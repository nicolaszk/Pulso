"""Passos 1 a 4 do pipeline: leitura dos CSVs, limpeza, extracao dos eventos e carga no banco.

  1. leitura   priorizacao.carga.carregar: os 3 CSVs como vieram + sha256
  2. limpeza   priorizacao.limpeza.limpar: CID, prioridade, municipio, duplicatas fundidas
               no mestre, saidas escritas nas observacoes, quarentena de eventos
  3. eventos   eventos validos, remapeados ao mestre e sem repetidos, entram PENDENTES
  4. banco     catalogos, pacientes, solicitacoes, eventos e a fila inicial: cada ativa
               avaliada so com o cadastro (CID, dor, limitacao, texto), sem nenhum evento.
               Os eventos mudam a fila depois, um por um (processamento.py), com aprovacao.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone

import pandas as pd
import psycopg

from .. import config, db
from ..db import Jsonb
from . import explicacao
from .avaliacao import CLASSE_SWALIS, avaliar
from .fila import conferir_regra_de_ouro, renumerar
from .processamento import estado_params

import build_features as bf
import gerar_seed
from priorizacao import config as regras
from priorizacao.carga import carregar as ler_csvs
from priorizacao.limpeza import limpar

# Campos da linha limpa que o motor le (montar_estado / triar)
CAMPOS_MOTOR = [
    "solicitacao_id", "paciente_id", "data_entrada_fila", "cid", "cid_exibicao", "oncologico", "dor",
    "limitacao", "prioridade_manual", "justificativa_clinica", "txt_justificativa", "txt_observacoes",
    "hba1c_ultima", "data_hba1c_ultima", "flag_oncologico", "flag_piora_clinica", "flag_diabetico",
    "cid_secundario", "comorbidades", "irma_com_evento", "duplicata_fundida", "pendencias_saida",
]
PRIORIDADE_MANUAL = {"alta": 1, "media": 2, "baixa": 3}


def carregar(con: psycopg.Connection, dataset=None, data_referencia=None, recriar: bool = False) -> dict:
    dataset = dataset or config.DATASET
    ref = pd.Timestamp(data_referencia or config.DATA_REFERENCIA)
    if db.banco_populado(con) and not recriar:
        raise RuntimeError("banco ja carregado; use --recriar para apagar e carregar de novo")
    iniciada = datetime.now(timezone.utc)

    brutos = ler_csvs(dataset)                                                       # 1
    lp = limpar(brutos.fila, brutos.eventos, brutos.procedimentos, ref, saidas_por_evento=False)  # 2
    eventos = _extrair_eventos(lp, brutos.eventos)                                   # 3

    db.aplicar_schema(con)                                                           # 4
    with con.transaction():
        exec_id = con.execute(
            """INSERT INTO execucao (tipo, data_referencia, regras_versao, hashes, relatorio, iniciada_em)
               VALUES ('carga', %s, %s, %s, %s, %s) RETURNING id""",
            (ref.date(), regras.REGRAS_VERSAO, Jsonb(brutos.hashes), Jsonb(lp.relatorio), iniciada),
        ).fetchone()["id"]
        medicos_por_esp, proc_esp, rng = _catalogos(con, brutos.procedimentos, dataset)
        _pacientes(con, brutos.fila, lp.solicitacoes)
        _solicitacoes(con, brutos.fila, lp.solicitacoes, medicos_por_esp, proc_esp, rng)
        con.cursor().executemany(
            """INSERT INTO evento_clinico (id, solicitacao_id, data_evento, tipo_evento, resultado,
               valor_numerico, descricao, origem, solicitacao_id_original, hash_conteudo)
               VALUES (%(evento_id)s, %(solicitacao_id)s, %(data_evento)s, %(tipo_evento)s, %(resultado)s,
               %(valor_numerico)s, %(descricao)s, %(origem)s, %(solicitacao_id_original)s, %(hash_conteudo)s)""",
            eventos)
        con.cursor().executemany(
            "INSERT INTO evento_quarentena (evento_id, motivo, registro, execucao_id) VALUES (%s, %s, %s, %s)",
            [(json.loads(q["registro_json"]).get("evento_id") or "?", q["motivo"],
              Jsonb(json.loads(q["registro_json"])), exec_id) for q in lp.quarentena])
        filas = _fila_inicial(con, lp.solicitacoes, ref)
        n_features = _features(con, dataset, ref)
        n_explicacoes = explicacao.importar_cache(con)
        con.execute("UPDATE execucao SET terminada_em = now() WHERE id = %s", (exec_id,))

    st = lp.solicitacoes["status"].value_counts().to_dict()
    return {"execucao": exec_id, "data_referencia": str(ref.date()), "solicitacoes": len(lp.solicitacoes),
            "status": {k: int(v) for k, v in st.items()}, "eventos_pendentes": len(eventos),
            "eventos_repetidos_descartados": lp.descartados_duplicados, "quarentena": len(lp.quarentena),
            "fila_inicial": filas, "features": n_features, "explicacoes_importadas": n_explicacoes}


# ---------------------------------------------------------------------------- 3. eventos
def _extrair_eventos(lp, eventos_brutos: pd.DataFrame) -> list[dict]:
    original = dict(zip(eventos_brutos["evento_id"], eventos_brutos["solicitacao_id"]))
    out = []
    for ev in (lp.eventos.to_dict("records") if not lp.eventos.empty else []):
        sid = ev["solicitacao_id"]
        out.append({
            "evento_id": ev["evento_id"], "solicitacao_id": sid,
            "data_evento": pd.Timestamp(ev["data_evento"]).date(),
            "tipo_evento": ev["tipo_evento"], "resultado": ev["resultado"],
            "valor_numerico": _num(ev["valor_numerico"]),
            "descricao": _txt(ev.get("descricao")) or "", "origem": _txt(ev.get("origem")) or "",
            "solicitacao_id_original": original.get(ev["evento_id"]) if original.get(ev["evento_id"]) != sid else None,
            "hash_conteudo": ev["hash_conteudo"],
        })
    return out


# ---------------------------------------------------------------------------- 4. banco
def _catalogos(con, procs: pd.DataFrame, dataset) -> tuple[dict, dict, random.Random]:
    """Especialidade, hospital, medico (sinteticos, de db/gerar_seed.py), procedimento, SWALIS, filas.
    Devolve o rng logo depois dos medicos: o gerar_seed.py sorteia os solicitantes com ele."""
    especialidades = sorted(set(procs["especialidade"]))
    esp_id = {nome: i for i, nome in enumerate(especialidades, start=1)}
    # mesma semente e ordem do gerar_seed.py: mesmos medicos e mesmos solicitantes do seed.sql
    rng = random.Random(gerar_seed.SEMENTE)
    medicos, medicos_por_esp = gerar_seed.gerar_medicos(especialidades, esp_id, rng)
    cur = con.cursor()
    cur.executemany("INSERT INTO especialidade (id, nome) OVERRIDING SYSTEM VALUE VALUES (%s, %s)",
                    [(i, n) for n, i in esp_id.items()])
    cur.executemany("INSERT INTO hospital (id, nome, municipio) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s)",
                    [(i, n, m) for i, (n, m) in enumerate(gerar_seed.HOSPITAIS, start=1)])
    cur.executemany("""INSERT INTO medico (id, nome, crm, especialidade_id, hospital_id)
                       OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, %s)""",
                    [(i, *m) for i, m in enumerate(medicos, start=1)])
    cur.executemany("""INSERT INTO procedimento (id, nome, especialidade_id, porte, risco_cirurgico,
                       duracao_media_min, necessita_uti) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    [(p["procedimento_id"], p["procedimento"], esp_id[p["especialidade"]], p["porte"],
                      int(p["risco_cirurgico"]), int(p["duracao_media_min"]), p["necessita_uti"])
                     for p in procs.to_dict("records")])
    swalis = pd.read_csv(dataset / "referencias" / "swalis.csv", dtype=str)
    cur.executemany("INSERT INTO swalis_classe (classe, descricao, prazo_maximo_dias, exemplos) VALUES (%s, %s, %s, %s)",
                    [(s["classe"], s["descricao"], int(s["prazo_maximo_dias"]), _txt(s.get("exemplos")))
                     for s in swalis.to_dict("records")])
    cur.executemany("INSERT INTO fila_grupo (codigo, nome, ordem, prazo_dias, classe_swalis) VALUES (%s, %s, %s, %s, %s)",
                    [(g, n, regras.ORDEM_FILA[g], p, CLASSE_SWALIS[g]) for g, n, p in regras.GRUPOS])
    proc_esp = {p["procedimento_id"]: esp_id[p["especialidade"]] for p in procs.to_dict("records")}
    return medicos_por_esp, proc_esp, rng


def _ordem_entrada(fila: pd.DataFrame) -> list[dict]:
    return sorted(fila.to_dict("records"), key=lambda r: (r["data_entrada_fila"], r["solicitacao_id"]))


def _pacientes(con, fila: pd.DataFrame, limpas: pd.DataFrame) -> None:
    """Atributos do paciente vem da solicitacao mais antiga (como no gerar_seed.py)."""
    municipio = dict(zip(limpas["solicitacao_id"], limpas["municipio"]))
    pacientes = {}
    for r in _ordem_entrada(fila):
        pid, nome = r["paciente_id"], _txt(r["nome_paciente"]) or ""
        if pid in pacientes:
            if pacientes[pid][1].isupper() and not nome.isupper():  # prefere a grafia que nao e toda maiuscula
                pacientes[pid][1] = nome
            continue
        comorb = [c.strip() for c in (_txt(r["comorbidades"]) or "").split(";") if c.strip()]
        pacientes[pid] = [pid, nome, r["sexo"], int(r["idade"]), municipio[r["solicitacao_id"]], r["uf"],
                          _int(r["distancia_hospital_km"]), [] if comorb == ["nenhuma"] else comorb]
    con.cursor().executemany(
        """INSERT INTO paciente (id, nome, sexo, idade, municipio, uf, distancia_hospital_km, comorbidades)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", sorted(pacientes.values()))


def _solicitacoes(con, fila: pd.DataFrame, limpas: pd.DataFrame, medicos_por_esp, proc_esp, rng) -> None:
    limpa = {r["solicitacao_id"]: r for r in limpas.to_dict("records")}
    linhas = []
    for r in _ordem_entrada(fila):
        sid = r["solicitacao_id"]
        lr = limpa[sid]
        motivo = None
        if lr["status"] == "duplicata":
            motivo = f"mesmo paciente e procedimento de {lr['mestre_id']}"
        elif lr["status"] == "saiu":
            motivo = lr["evidencia_saida"]
        prio = lr["prioridade_manual"]
        linhas.append({
            "id": sid, "paciente_id": r["paciente_id"], "procedimento_id": r["procedimento_id"],
            "medico": rng.choice(medicos_por_esp[proc_esp[r["procedimento_id"]]]),
            "cid": lr["cid"], "cid_descricao": _txt(r["cid_descricao"]) or "",
            "cid_secundario": (_txt(r["cid_secundario"]) or "").upper().replace(".", "") or None,
            "asa": _int(r["asa"]), "dor": _int(r["intensidade_dor_eva"]),
            "limitacao": _txt(r["limitacao_funcional"]),
            "justificativa": _txt(r["justificativa_clinica"]) or "", "observacoes": _txt(r["observacoes"]),
            "entrada": r["data_entrada_fila"].date(),
            "prioridade": prio if prio in PRIORIDADE_MANUAL else None,
            "revisao": r["data_ultima_revisao_prioridade"].date(),
            "hba1c": _num(r["hba1c_ultima"]), "data_hba1c": _data(r["data_hba1c_ultima"]),
            "pre_anestesica": r["avaliacao_pre_anestesica"], "exames": r["exames_pre_op_validos"] == "sim",
            "status": lr["status"], "duplicata_de": lr["mestre_id"] if lr["status"] == "duplicata" else None,
            "motivo_status": motivo, "dados_motor": Jsonb(_json({c: lr.get(c) for c in CAMPOS_MOTOR})),
        })
    linhas.sort(key=lambda s: s["status"] == "duplicata")  # a duplicata referencia o mestre
    con.cursor().executemany("""
        INSERT INTO solicitacao (id, paciente_id, procedimento_id, hospital_id, medico_solicitante_id,
            cid_principal, cid_descricao, cid_secundario, asa, intensidade_dor_eva, limitacao_funcional,
            justificativa_clinica, observacoes, data_entrada_fila, prioridade_regulacao,
            data_ultima_revisao_prioridade, hba1c_ultima, data_hba1c_ultima, avaliacao_pre_anestesica,
            exames_pre_op_validos, status, duplicata_de, motivo_status, dados_motor)
        VALUES (%(id)s, %(paciente_id)s, %(procedimento_id)s, 1, %(medico)s, %(cid)s, %(cid_descricao)s,
            %(cid_secundario)s, %(asa)s, %(dor)s, %(limitacao)s, %(justificativa)s, %(observacoes)s,
            %(entrada)s, %(prioridade)s, %(revisao)s, %(hba1c)s, %(data_hba1c)s, %(pre_anestesica)s,
            %(exames)s, %(status)s, %(duplicata_de)s, %(motivo_status)s, %(dados_motor)s)""", linhas)


def _fila_inicial(con, limpas: pd.DataFrame, ref) -> dict:
    """Cada ativa avaliada sem eventos. posicao_inicial = metodo atual (prioridade manual,
    depois entrada), a base do "antes e depois" do db/README.md."""
    ativas = limpas[limpas["status"] == "ativa"]
    avs = [avaliar(_json({c: r.get(c) for c in CAMPOS_MOTOR}), [], ref) for r in ativas.to_dict("records")]
    entrada = dict(zip(ativas["solicitacao_id"], ativas["data_entrada_fila"]))
    prio = dict(zip(ativas["solicitacao_id"], ativas["prioridade_manual"]))
    inicial = sorted(entrada, key=lambda s: (PRIORIDADE_MANUAL.get(prio[s], 4), entrada[s], s))
    pos_inicial = {s: i for i, s in enumerate(inicial, start=1)}

    cur = con.cursor()
    cur.executemany("""INSERT INTO estado_paciente (solicitacao_id, data_calculo, fila, sair, data_limite_efetiva,
                       n_sinais, dor, sem_urgencia, motivos, justificativa, sinais, evidencias, marcacoes,
                       pendencias, proxima_revisao, ultimo_evento_id, atualizado_em)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                    [estado_params(av, None) for av in avs])
    # posicao_final provisoria (= inicial) so para satisfazer o CHECK; renumerar() poe a ordem do motor
    cur.executemany("""INSERT INTO fila_priorizada (solicitacao_id, posicao_inicial, posicao_final, justificativa,
                       classe_swalis, fila, data_limite_efetiva, n_sinais, dor, marcacoes, atualizada_em)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                    [(av.solicitacao_id, pos_inicial[av.solicitacao_id], pos_inicial[av.solicitacao_id],
                      av.justificativa, av.classe_swalis, av.fila, av.data_limite_efetiva, av.n_sinais, av.dor,
                      Jsonb(av.marcacoes)) for av in avs])
    renumerar(con)
    conferir_regra_de_ouro(con)
    tamanhos = {g: 0 for g, _, _ in regras.GRUPOS}
    for av in avs:
        tamanhos[av.fila] += 1
    return tamanhos


def _features(con, dataset, ref) -> int:
    """build_features.py na data de referencia, uma linha por solicitacao (para JEV e detalhe)."""
    fila, ev, procs = bf.load(dataset)
    feats, _ = bf.build(fila, ev, procs, ref)
    linhas = json.loads(feats.to_json(orient="records", date_format="iso"))
    ids = {r["id"] for r in con.execute("SELECT id FROM solicitacao").fetchall()}
    dados = [(r["solicitacao_id"], ref.date(), Jsonb(r)) for r in linhas if r["solicitacao_id"] in ids]
    con.cursor().executemany(
        "INSERT INTO features_paciente (solicitacao_id, data_referencia, features) VALUES (%s, %s, %s)", dados)
    return len(dados)


# ---------------------------------------------------------------------------- conversoes
def _vazio(v) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, dict)):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _txt(v) -> str | None:
    if _vazio(v):
        return None
    s = str(v).strip()
    return s or None


def _int(v) -> int | None:
    return None if _vazio(v) or str(v).strip() == "" else int(float(v))


def _num(v) -> float | None:
    return None if _vazio(v) or str(v).strip() == "" else float(v)


def _data(v):
    return None if _vazio(v) else pd.Timestamp(v).date()


def _json(d: dict) -> dict:
    """Valores do pandas/numpy -> JSON (datas em ISO, NaN -> None)."""
    out = {}
    for k, v in d.items():
        if isinstance(v, (list, dict)):
            out[k] = v
        elif _vazio(v):
            out[k] = None
        elif isinstance(v, pd.Timestamp):
            out[k] = v.date().isoformat()
        elif hasattr(v, "item"):  # numpy
            out[k] = v.item()
        else:
            out[k] = v
    return out
