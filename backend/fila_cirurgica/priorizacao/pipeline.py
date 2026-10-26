# -*- coding: utf-8 -*-
"""Encadeia os passos 1 a 6: carga_inicial(dataset, data_referencia, banco, saida).

Carga inicial em banco ja populado e recusada, salvo recriar=True.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import banco as banco_mod
from . import config
from .carga import carregar
from .classificadores import REGISTRO, ordenar_filas
from .limpeza import limpar
from .saida import gerar_saida
from .sinais import montar_estado
from .triagem import triar

_TEXTO_MOTIVO = {
    "maligno": "maligno", "oncologico": "oncologico",
    "biopsia_positiva": "biopsia positiva", "progressao_imagem": "progressao em imagem",
    "reavaliacao_piora": "reavaliacao com piora", "pronto_socorro": "pronto-socorro",
    "internacao": "internacao", "relata_piora": "relata piora", "obs_piora": "piora em observacao",
    "texto_alarme": "sinal de alarme no texto", "texto_agudo": "quadro agudo no texto",
    "texto_suspeita": "suspeita no texto", "cid_urgente": "CID urgente",
    "cid_incerto": "CID de comportamento incerto", "piora_expirada": "piora antiga (>180 d)",
    "dor_alta": "dor alta", "dor_moderada": "dor moderada",
    "limitacao_grave": "limitacao grave", "limitacao_moderada": "limitacao moderada",
    "eletivo_estavel": "eletivo estavel",
}


@dataclass
class Resumo:
    data_referencia: str
    total_csv: int
    ativas: int
    duplicatas: int
    saidas: int
    quarentena: int
    duplicados_descartados: int
    tamanhos: dict
    checagens: list
    arquivos: list
    versao_id: int
    falhas_classificador: list


def _iso(ts) -> str | None:
    if ts is None or (isinstance(ts, float) and ts != ts):
        return None
    t = pd.Timestamp(ts)
    return None if t is pd.NaT or t != t else t.date().isoformat()


def _motivo_texto(estado, motivos) -> str:
    partes = []
    for sinal in motivos[:2]:
        rotulo = _TEXTO_MOTIVO.get(sinal, sinal)
        evid = estado.evidencias.get(sinal)
        if evid:
            ev = evid[-1]
            data = ev.get("data")
            trecho = (ev.get("trecho") or "").strip()
            det = " ".join(x for x in [_data_br(data), trecho] if x)
            partes.append(f"{rotulo}{(' — ' + det) if det else ''}")
        else:
            partes.append(rotulo)
    return "; ".join(partes)


def _data_br(iso) -> str:
    if not iso:
        return ""
    a, m, d = str(iso)[:10].split("-")
    return f"{d}/{m}/{a}"


def carga_inicial(dataset, data_referencia=config.DATA_REFERENCIA_PADRAO,
                  banco="saida/fila.sqlite", saida="saida", recriar=False) -> Resumo:
    ref = pd.Timestamp(data_referencia)
    iniciada = datetime.now(timezone.utc).isoformat()

    # passo 1
    brutos = carregar(dataset)
    total_csv = len(brutos.fila)

    # passo 2
    lp = limpar(brutos.fila, brutos.eventos, brutos.procedimentos, ref)
    sol = lp.solicitacoes
    ativas = sol[sol["status"] == "ativa"]

    eventos_por_sol: dict[str, list] = {}
    for ev in lp.eventos.to_dict("records") if not lp.eventos.empty else []:
        eventos_por_sol.setdefault(ev["solicitacao_id"], []).append(ev)

    # passos 3 e 4 (por paciente)
    estados, triagens, detalhe = {}, {}, []
    for row in ativas.to_dict("records"):
        sid = row["solicitacao_id"]
        est = montar_estado(row, eventos_por_sol.get(sid, []), ref)
        tri = triar(est, ref, pendencias_saida=row.get("pendencias_saida") or [])
        estados[sid] = est
        triagens[sid] = tri

    # passo 5
    triados = pd.DataFrame([{
        "solicitacao_id": sid, "fila": triagens[sid].fila,
        "data_entrada_fila": estados[sid].data_entrada,
    } for sid in triagens])
    limites = ordenar_filas(triados, REGISTRO, ref)
    limite_de = {r["solicitacao_id"]: r for r in limites.to_dict("records")}
    falhas_clf = limites.attrs.get("falhas", [])

    # montar detalhe para a saida
    for sid, est in estados.items():
        tri = triagens[sid]
        clf = limite_de[sid]
        marcacoes = list(tri.marcacoes)
        for mc in clf.get("marcacoes_classificador", []):
            marcacoes.append({"marcacao": mc, "severidade": "media"})
        detalhe.append({
            "solicitacao_id": sid,
            "paciente_id": est.paciente_id,
            "fila": tri.fila,
            "ordem_fila": config.ORDEM_FILA[tri.fila],
            "prazo": config.PRAZO_FILA[tri.fila],
            "dias_em_fila": est.dias_em_fila,
            "data_entrada_iso": _iso(est.data_entrada),
            "data_limite_efetiva": clf["data_limite_efetiva"],
            "n_sinais": est.n_sinais(),
            "dor": est.dor,
            "cid_exibicao": est.cid_exibicao,
            "oncologico": est.oncologico,
            "rotulos": tri.rotulos,
            "motivos": [_TEXTO_MOTIVO.get(m, m) for m in tri.motivos],
            "motivo_texto": _motivo_texto(est, tri.motivos),
            "marcacoes": marcacoes,
            "pendencias": tri.pendencias,
            "proxima_revisao": tri.proxima_revisao,
            "classificador": clf["classificador"],
            "classificador_versao": clf["classificador_versao"],
            "componentes": clf["componentes"],
            "prioridade_manual": est.prioridade_manual,
            "sem_urgencia": _sem_urgencia(est),
        })

    fora = _fora_da_fila(sol)

    # passo 6 (gera arquivos; regra de ouro falha => nada e gravado)
    out = gerar_saida(detalhe, fora, lp.quarentena, lp.relatorio, total_csv, saida, str(ref.date()))

    # banco (transacao unica)
    con = banco_mod.conectar(banco)
    banco_mod.criar_esquema(con)
    if banco_mod.ja_populado(con) and not recriar:
        con.close()
        raise RuntimeError("banco ja populado; use recriar=True (--recriar) para a carga inicial")
    if recriar:
        con.close()
        banco_mod.recriar(banco)
        con = banco_mod.conectar(banco)
        banco_mod.criar_esquema(con)

    terminada = datetime.now(timezone.utc).isoformat()
    versao_id = banco_mod.gravar_carga_inicial(
        con,
        execucao={"tipo": "carga_inicial", "data_referencia": str(ref.date()),
                  "hashes": brutos.hashes, "iniciada_em": iniciada, "terminada_em": terminada},
        regras={"versao": config.REGRAS_VERSAO, "config": config.config_json()},
        solicitacoes=_solicitacoes_db(sol),
        eventos=_eventos_db(lp.eventos),
        quarentena=lp.quarentena,
        estados=_estados_db(estados, eventos_por_sol),
        itens=_itens_db(out.itens),
        n_ativas=len(ativas),
    )
    con.close()

    vc = sol["status"].value_counts().to_dict()
    return Resumo(
        data_referencia=str(ref.date()),
        total_csv=total_csv,
        ativas=int(vc.get("ativa", 0)),
        duplicatas=int(vc.get("duplicata", 0)),
        saidas=int(vc.get("saiu", 0)),
        quarentena=len(lp.quarentena),
        duplicados_descartados=lp.descartados_duplicados,
        tamanhos=out.tamanhos,
        checagens=out.checagens,
        arquivos=[str(a) for a in out.arquivos],
        versao_id=versao_id,
        falhas_classificador=falhas_clf,
    )


def _sem_urgencia(est) -> bool:
    dor = est.dor if est.dor is not None else 0
    lim = est.limitacao if est.limitacao is not None else 0
    return (not est.maligno and dor <= 3 and lim <= 1 and not est.cid_urgente
            and not est.piora_qualquer and not est.biopsia_positiva
            and not est.texto_alarme and not est.texto_agudo and not est.texto_suspeita)


def _fora_da_fila(sol: pd.DataFrame) -> list[dict]:
    fora = []
    for row in sol.to_dict("records"):
        if row["status"] == "duplicata":
            fora.append({"solicitacao_id": row["solicitacao_id"], "status": "duplicata",
                         "mestre_id": row.get("mestre_id"), "evidencia": f"fundida em {row.get('mestre_id')}"})
        elif row["status"] == "saiu":
            fora.append({"solicitacao_id": row["solicitacao_id"], "status": "saiu",
                         "mestre_id": None, "evidencia": row.get("evidencia_saida") or ""})
    return fora


def _solicitacoes_db(sol: pd.DataFrame) -> list[dict]:
    campos = ["cid", "cid_exibicao", "oncologico", "dor", "limitacao", "prioridade_manual",
              "municipio", "distancia_hospital_km", "procedimento_id", "idade",
              "data_entrada_fila", "dias_em_fila"]
    out = []
    for row in sol.to_dict("records"):
        dados = {}
        for c in campos:
            v = row.get(c)
            if isinstance(v, pd.Timestamp):
                v = _iso(v)
            elif isinstance(v, float) and v != v:
                v = None
            dados[c] = v
        out.append({
            "solicitacao_id": row["solicitacao_id"], "paciente_id": row["paciente_id"],
            "mestre_id": row.get("mestre_id"), "status": row["status"], "dados": dados,
            "evidencia_saida": row.get("evidencia_saida"),
        })
    return out


def _eventos_db(eventos: pd.DataFrame) -> list[dict]:
    if eventos.empty:
        return []
    out = []
    for ev in eventos.to_dict("records"):
        out.append({
            "evento_id": ev.get("evento_id"), "solicitacao_id": ev["solicitacao_id"],
            "paciente_id": ev.get("paciente_id"), "data_evento": _iso(ev.get("data_evento")),
            "data_recebimento": _iso(ev.get("data_recebimento")), "tipo": ev.get("tipo_evento"),
            "resultado": ev.get("resultado"), "valor": ev.get("valor_numerico"),
            "descricao": ev.get("descricao"), "origem": ev.get("origem"),
            "hash_conteudo": ev.get("hash_conteudo"),
        })
    return out


def _estados_db(estados: dict, eventos_por_sol: dict) -> list[dict]:
    out = []
    for sid, est in estados.items():
        evs = eventos_por_sol.get(sid, [])
        bruto = json.dumps([e.get("hash_conteudo") for e in evs], sort_keys=True) + est.cid + str(est.dor)
        out.append({
            "solicitacao_id": sid,
            "sinais": sorted(est.sinais_validos),
            "evidencias": est.evidencias,
            "hash_entrada": hashlib.sha256(bruto.encode()).hexdigest(),
        })
    return out


def _itens_db(itens: list[dict]) -> list[dict]:
    out = []
    for r in itens:
        out.append({
            "solicitacao_id": r["solicitacao_id"], "fila": r["fila"], "ordem_fila": r["ordem_fila"],
            "data_limite_efetiva": r["data_limite_efetiva"], "posicao": r["posicao"],
            "posicao_fila": r["posicao_fila"], "classificador": r["classificador"],
            "classificador_versao": r["classificador_versao"], "componentes": r["componentes"],
            "rotulos": r["rotulos"], "marcacoes": r["marcacoes"], "pendencias": r["pendencias"],
            "proxima_revisao": r["proxima_revisao"], "justificativa": r["justificativa"],
        })
    return out
