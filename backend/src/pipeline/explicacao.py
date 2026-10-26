"""Explicacao em linguagem clara, escrita por um LLM a partir dos fatos do motor.

O LLM so reescreve: recebe os FATOS (fila, prazo, espera, motivo tecnico com as evidencias,
alertas, pendencias, pedido aguardando o medico) e devolve 2-3 frases. Nunca muda a fila.
Depois da resposta, `conferir` recusa o texto que cita numero ou data, codigo de fila ou
termo oncologico que nao esta nos fatos; uma nova tentativa com o motivo e, se falhar de
novo, vale o texto do template (a justificativa de sempre).

Cache em `explicacao`, chaveado pelo hash dos fatos: os mesmos fatos dao o mesmo texto
(fila reproduzivel); um evento novo muda os fatos e gera outro texto.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import psycopg

from .. import config
from ..llm import LLM, LLMIndisponivel
from priorizacao import config as regras

VERSAO = "2"  # subir quando mudar o prompt ou os fatos: invalida o cache
LIMITE = 400  # caracteres

SISTEMA = """Voce explica a fila de cirurgias eletivas do SUS para o medico regulador, em portugues claro.
Voce recebe FATOS calculados pelo sistema e reescreve o motivo tecnico em linguagem simples.
Regras:
- Use somente os FATOS. Nao invente exames, datas, numeros, diagnosticos nem sintomas.
- Nao faca contas: copie numeros e datas exatamente como estao nos FATOS.
- Nao decida e nao recomende tratamento: o sistema propoe e o medico decide.
- Chame a fila pelo nome (ex.: "Deterioracao recente"), sem os codigos G1a, G4 etc.
- Nao fale em cancer, tumor ou malignidade se os FATOS nao falarem.
- 2 a 3 frases, no maximo 400 caracteres, sem listas e sem titulo.
Responda somente com JSON: {"texto": "..."}"""

PEDIDO = {
    "solicitacao": "Explique por que o sistema coloca este paciente nesta fila e o que o medico precisa "
                   "olhar (alertas, pendencias, pedido aguardando decisao), se houver.",
    "mudanca": "Explique ao medico o que o sistema esta pedindo e por que, com base nas evidencias.",
}

MARCACOES = {
    "atualizar_cid": "biopsia positiva com CID ainda nao oncologico: atualizar o CID",
    "conflito_laudos": "laudos de biopsia que se contradizem",
    "somente_texto": "fila sustentada so pelo texto do medico, sem evento que confirme",
    "texto_antigo": "o texto que sustenta a fila tem mais de um ano",
    "confirmar_saida_g4": "a piora tem mais de 180 dias: confirmar se continua nesta fila",
    "justificativa_pobre": "justificativa do medico solicitante muito curta",
    "dados_faltantes": "dor ou limitacao funcional nao informadas",
    "revisao_classificador": "data limite calculada pelo padrao: revisar",
}
PENDENCIAS = {
    "nao_atendeu_2x": "nao atendeu duas ou mais ligacoes",
    "faltas_2x": "faltou duas ou mais vezes",
    "hba1c_alta": "HbA1c acima de 8,5% (preparo para a cirurgia)",
    "duplicata_fundida": "tinha outra solicitacao igual, fundida nesta",
    "irma_com_evento": "outra solicitacao do mesmo paciente teve biopsia positiva ou internacao",
    "confirmar_saida": "disse que nao quer mais operar no momento: confirmar",
    "sem_contato": "sem contato (telefone ou endereco)",
}
TIPO_PEDIDO = {"subir": "subir de fila", "descer": "descer de fila", "sair": "tirar da fila"}
TIPO_EVENTO = {"biopsia": "biopsia", "hba1c": "HbA1c", "pronto_socorro": "pronto-socorro", "internacao": "internacao",
               "exame_imagem": "exame de imagem", "consulta_reavaliacao": "reavaliacao",
               "contato_telefonico": "contato telefonico", "falta": "falta"}
N_EVENTOS = 6


# ---------------------------------------------------------------------------- conferencia
_NUM = re.compile(r"\d+")
_CODIGO = re.compile(r"\bG[1-7][ab]?\b")
_TERMOS_ONCO = ("cancer", "malign", "tumor", "neoplasi", "carcinom", "metasta")
# "nao ha pendencias", "sem alertas"... quando os fatos tem pendencias/alertas
_NEGA = re.compile(r"\b(?:nao ha|nao existem?|sem|nenhuma?)\s+(?:\w+\s+){0,2}?(pendencia|alerta)")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def conferir(texto: str, fatos: str) -> list[str]:
    """Problemas do texto em relacao aos fatos (lista vazia = aceito)."""
    if not texto.strip():
        return ["texto vazio"]
    problemas = []
    if len(texto) > LIMITE:
        problemas.append(f"texto com {len(texto)} caracteres (maximo {LIMITE})")
    numeros = {int(n) for n in _NUM.findall(fatos)}
    fora = sorted({n for n in _NUM.findall(texto) if int(n) not in numeros}, key=int)
    if fora:
        problemas.append("numeros ou datas que nao estao nos fatos: " + ", ".join(fora))
    codigos = sorted(set(_CODIGO.findall(texto)) - set(_CODIGO.findall(fatos)))
    if codigos:
        problemas.append("fila que nao esta nos fatos: " + ", ".join(codigos))
    t, f = _norm(texto), _norm(fatos)
    termos = [x for x in _TERMOS_ONCO if x in t and x not in f]
    if termos:
        problemas.append("termo oncologico que nao esta nos fatos: " + ", ".join(termos))
    filas = [n for _, n, _ in regras.GRUPOS if _norm(n) in t and _norm(n) not in f]
    if filas:
        problemas.append("fila que nao esta nos fatos: " + ", ".join(filas))
    negados = sorted({m for m in _NEGA.findall(t) if f"{m}s:" in f or f"{m}s para o medico:" in f})
    if negados:
        problemas.append("diz que nao ha " + ", ".join(f"{m}s" for m in negados) + ", mas os fatos tem")
    return problemas


def _cortar(texto: str) -> str:
    """Acima do limite, corta na ultima frase completa que cabe."""
    texto = " ".join(texto.split())
    if len(texto) <= LIMITE:
        return texto
    fim = max(texto.rfind(p, 0, LIMITE) for p in (". ", "! ", "? "))
    if texto[LIMITE - 1] in ".!?":
        fim = LIMITE - 1
    return texto[: fim + 1] if fim > 0 else texto


# ---------------------------------------------------------------------------- fatos
def _br(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "?"


def _cid(c: str) -> str:
    return c[:3] + "." + c[3:] if len(c) > 3 else c


def _espera_e_prazo(entrada: date, limite: date, ref: date) -> list[str]:
    linhas = [f"Entrada na fila: {_br(entrada)}. Espera ate {_br(ref)}: {(ref - entrada).days} dias."]
    dias = (limite - ref).days
    situacao = f"vencida ha {-dias} dias" if dias < 0 else ("vence hoje" if dias == 0 else f"faltam {dias} dias")
    linhas.append(f"Data limite para operar: {_br(limite)} ({situacao}).")
    return linhas


def fatos(con: psycopg.Connection, alvo: str, alvo_id: str) -> tuple[str, str] | None:
    """(fatos em texto, texto do template). None se o alvo nao existe."""
    if alvo == "solicitacao":
        return _fatos_solicitacao(con, alvo_id)
    if alvo == "mudanca":
        return _fatos_mudanca(con, int(alvo_id))
    raise ValueError("alvo deve ser solicitacao ou mudanca")


def _fatos_solicitacao(con, sid: str):
    r = con.execute("""
        SELECT s.cid_principal, s.cid_descricao, s.data_entrada_fila, p.nome AS procedimento, pa.idade,
               e.fila, g.nome AS fila_nome, g.prazo_dias, e.data_limite_efetiva, e.justificativa, e.marcacoes,
               e.pendencias, e.data_calculo, e.sair,
               fp.fila AS fila_oficial, go.nome AS fila_oficial_nome,
               m.tipo AS pedido_tipo, m.fila_proposta AS pedido_fila, gm.nome AS pedido_fila_nome
        FROM estado_paciente e
        JOIN solicitacao s ON s.id = e.solicitacao_id
        JOIN procedimento p ON p.id = s.procedimento_id
        JOIN paciente pa ON pa.id = s.paciente_id
        JOIN fila_grupo g ON g.codigo = e.fila
        LEFT JOIN fila_priorizada fp ON fp.solicitacao_id = e.solicitacao_id
        LEFT JOIN fila_grupo go ON go.codigo = fp.fila
        LEFT JOIN solicitacao_mudanca m ON m.solicitacao_id = e.solicitacao_id AND m.status = 'pendente'
        LEFT JOIN fila_grupo gm ON gm.codigo = m.fila_proposta
        WHERE e.solicitacao_id = %s AND s.status = 'ativa'""", (sid,)).fetchone()
    if r is None:
        return None
    linhas = [f"Paciente: {r['idade']} anos.",
              f"Procedimento: {r['procedimento']}.",
              f"Diagnostico: CID {_cid(r['cid_principal'])}, {r['cid_descricao']}.",
              f"Fila indicada pelo sistema: {r['fila_nome']} ({r['fila']}), prazo de {r['prazo_dias']} dias.",
              *_espera_e_prazo(r["data_entrada_fila"], r["data_limite_efetiva"], r["data_calculo"]),
              f"Motivo tecnico: {r['justificativa']}"]
    linhas += _eventos(con, sid, r["data_calculo"])
    alertas = [MARCACOES[m["marcacao"]] for m in r["marcacoes"] if m["marcacao"] in MARCACOES]
    if alertas:
        linhas.append("Alertas para o medico: " + "; ".join(alertas) + ".")
    pend = [PENDENCIAS[p] for p in r["pendencias"] if p in PENDENCIAS]
    if pend:
        linhas.append("Pendencias: " + "; ".join(pend) + ".")
    if r["pedido_tipo"] == "sair":
        linhas.append("Ha um evento de saida (desistencia ou cirurgia em outro servico): pedido para tirar da fila "
                      "aguardando o medico.")
    elif r["pedido_tipo"]:
        linhas.append(f"Fila oficial hoje: {r['fila_oficial_nome']} ({r['fila_oficial']}). Pedido para "
                      f"{TIPO_PEDIDO[r['pedido_tipo']]} para {r['pedido_fila_nome']} ({r['pedido_fila']}) "
                      "aguardando o medico.")
    elif r["fila_oficial"] is None:
        linhas.append("Fora da fila oficial.")
    return "\n".join(linhas), r["justificativa"]


def _fatos_mudanca(con, mid: int):
    r = con.execute("""
        SELECT m.*, s.cid_principal, s.cid_descricao, s.data_entrada_fila, p.nome AS procedimento, pa.idade,
               ga.nome AS de_nome, ga.prazo_dias AS de_prazo, gp.nome AS para_nome, gp.prazo_dias AS para_prazo
        FROM solicitacao_mudanca m
        JOIN solicitacao s ON s.id = m.solicitacao_id
        JOIN procedimento p ON p.id = s.procedimento_id
        JOIN paciente pa ON pa.id = s.paciente_id
        JOIN fila_grupo ga ON ga.codigo = m.fila_atual
        LEFT JOIN fila_grupo gp ON gp.codigo = m.fila_proposta
        WHERE m.id = %s""", (mid,)).fetchone()
    if r is None:
        return None
    linhas = [f"Pedido do sistema: {TIPO_PEDIDO[r['tipo']]}.",
              f"De: {r['de_nome']} ({r['fila_atual']}), prazo de {r['de_prazo']} dias. Posicao hoje: {r['posicao_atual']}."]
    if r["tipo"] != "sair":
        linhas.append(f"Para: {r['para_nome']} ({r['fila_proposta']}), prazo de {r['para_prazo']} dias. "
                      f"Posicao estimada se aprovado: {r['posicao_proposta']}.")
    linhas += [f"Paciente: {r['idade']} anos.",
               f"Procedimento: {r['procedimento']}.",
               f"Diagnostico: CID {_cid(r['cid_principal'])}, {r['cid_descricao']}.",
               f"Entrada na fila: {_br(r['data_entrada_fila'])}. Espera ate {_br(r['data_referencia'])}: "
               f"{(r['data_referencia'] - r['data_entrada_fila']).days} dias.",
               f"Motivo tecnico: {r['motivo']}"]
    evidencias = _evidencias(con, r["evidencias"])
    if evidencias:
        linhas.append("Evidencias:")
        linhas += [f"- {e}" for e in evidencias]
    linhas += _eventos(con, r["solicitacao_id"], r["data_referencia"])
    if r["oncologico"]:
        linhas.append("CID de neoplasia maligna: o sistema nunca rebaixa este paciente.")
    situacao = {"pendente": "aguardando decisao do medico (aprovar ou rejeitar)"}.get(r["status"], r["status"])
    linhas.append(f"Situacao do pedido: {situacao}.")
    return "\n".join(linhas), r["motivo"]


def _eventos(con, sid: str, ate: date) -> list[str]:
    """Os eventos mais recentes ja processados, em ordem de data."""
    evs = con.execute("""SELECT data_evento, tipo_evento, resultado, valor_numerico, descricao, origem
                         FROM evento_clinico WHERE solicitacao_id = %s AND processado_em IS NOT NULL
                         AND data_evento <= %s ORDER BY data_evento DESC, id DESC LIMIT %s""",
                      (sid, ate, N_EVENTOS)).fetchall()
    if not evs:
        return ["Eventos registrados durante a espera: nenhum."]
    linhas = ["Eventos registrados durante a espera (os mais recentes):"]
    for e in reversed(evs):
        valor = ""
        if e["valor_numerico"] is not None:
            valor = f" {e['valor_numerico']:g}%" if e["tipo_evento"] == "hba1c" else f" {e['valor_numerico']:g} dias"
        resultado = e["resultado"].replace("_", " ")
        linhas.append(f"- {_br(e['data_evento'])}, {TIPO_EVENTO.get(e['tipo_evento'], e['tipo_evento'])} "
                      f"({resultado}){valor}, {e['origem']}: \"{e['descricao']}\"")
    return linhas


def _evidencias(con, evidencias: list) -> list[str]:
    out = []
    for e in evidencias:
        if e.get("trecho") is None and e.get("evento_id"):  # pedido de saida guarda so o evento
            ev = con.execute("SELECT data_evento, origem, descricao FROM evento_clinico WHERE id = %s",
                             (e["evento_id"],)).fetchone()
            if ev:
                e = {"data": ev["data_evento"].isoformat(), "origem": ev["origem"], "trecho": ev["descricao"]}
        data = "/".join(reversed(e["data"].split("-"))) if e.get("data") else None
        partes = [x for x in (data, e.get("origem")) if x]
        out.append(f"{', '.join(partes)}: \"{e.get('trecho') or ''}\"" if partes else f"\"{e.get('trecho') or ''}\"")
    return out


# ---------------------------------------------------------------------------- geracao + cache
def _hash(fatos_txt: str) -> str:
    return hashlib.sha256(f"{VERSAO}\n{SISTEMA}\n{fatos_txt}".encode()).hexdigest()


def em_cache(con: psycopg.Connection, alvo: str, alvo_id: str) -> str | None:
    """Texto aceito para os fatos de agora, se ja foi gerado (sem chamar o LLM)."""
    f = fatos(con, alvo, str(alvo_id))
    if f is None:
        return None
    r = con.execute("""SELECT texto FROM explicacao WHERE alvo = %s AND alvo_id = %s AND hash_fatos = %s
                       AND status = 'ok' ORDER BY id DESC LIMIT 1""", (alvo, str(alvo_id), _hash(f[0]))).fetchone()
    return r["texto"] if r else None


def explicar(con: psycopg.Connection, alvo: str, alvo_id, llm: LLM | None = None, gerar: bool = True,
             tentativas: int = 2) -> dict | None:
    """Explicacao do alvo ('solicitacao' ou 'mudanca'). Sem LLM, ou texto recusado, vale o template."""
    alvo_id = str(alvo_id)
    f = fatos(con, alvo, alvo_id)
    if f is None:
        return None
    fatos_txt, template = f
    h = _hash(fatos_txt)
    base = {"alvo": alvo, "alvo_id": alvo_id, "fatos": fatos_txt}
    ok = con.execute("""SELECT texto, provedor, modelo FROM explicacao WHERE alvo = %s AND alvo_id = %s
                        AND hash_fatos = %s AND status = 'ok' ORDER BY id DESC LIMIT 1""",
                     (alvo, alvo_id, h)).fetchone()
    if ok:
        return {**base, "texto": ok["texto"], "fonte": "llm", "em_cache": True,
                "provedor": ok["provedor"], "modelo": ok["modelo"]}
    if not gerar:
        return {**base, "texto": template, "fonte": "template", "em_cache": False, "motivo": "sem texto gerado"}
    try:
        llm = llm or LLM()
    except LLMIndisponivel as exc:
        return {**base, "texto": template, "fonte": "template", "em_cache": False, "motivo": str(exc)}
    recusada = con.execute("""SELECT motivo_rejeicao FROM explicacao WHERE alvo = %s AND alvo_id = %s
                              AND hash_fatos = %s AND provedor = %s AND modelo = %s""",
                           (alvo, alvo_id, h, llm.provedor, llm.modelo)).fetchone()
    if recusada:  # este modelo ja falhou com estes fatos: nao gasta outra chamada
        return {**base, "texto": template, "fonte": "template", "em_cache": True,
                "motivo": recusada["motivo_rejeicao"], "provedor": llm.provedor, "modelo": llm.modelo}

    usuario = f"{PEDIDO[alvo]}\n\nFATOS:\n{fatos_txt}"
    texto, problemas, latencia, n = "", [], 0.0, 0
    for n in range(1, tentativas + 1):
        try:
            resp, seg = llm.json(SISTEMA, usuario)
        except LLMIndisponivel as exc:  # fora do ar: nao grava, tenta de novo da proxima vez
            return {**base, "texto": template, "fonte": "template", "em_cache": False, "motivo": str(exc)}
        latencia += seg
        texto = _cortar(str(resp.get("texto") or ""))
        problemas = conferir(texto, fatos_txt)
        if not problemas:
            break
        usuario = (f"{PEDIDO[alvo]}\n\nFATOS:\n{fatos_txt}\n\nSua resposta anterior foi recusada "
                   f"({'; '.join(problemas)}). Reescreva usando apenas os FATOS.")
    status = "rejeitada" if problemas else "ok"
    con.execute("""INSERT INTO explicacao (alvo, alvo_id, hash_fatos, fatos, status, texto, motivo_rejeicao,
                   provedor, modelo, tentativas, latencia_s) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (alvo, alvo_id, hash_fatos, provedor, modelo) DO NOTHING""",
                (alvo, alvo_id, h, fatos_txt, status, None if problemas else texto,
                 "; ".join(problemas) or None, llm.provedor, llm.modelo, n, latencia))
    if problemas:
        return {**base, "texto": template, "fonte": "template", "em_cache": False, "provedor": llm.provedor,
                "modelo": llm.modelo, "motivo": "; ".join(problemas), "texto_recusado": texto}
    return {**base, "texto": texto, "fonte": "llm", "em_cache": False, "provedor": llm.provedor,
            "modelo": llm.modelo, "latencia_s": latencia, "tentativas": n}


# ---------------------------------------------------------------------------- cache em arquivo
_CAMPOS = ("alvo", "alvo_id", "hash_fatos", "provedor", "modelo", "texto", "fatos", "tentativas", "latencia_s")


def salvar_cache(con: psycopg.Connection, caminho=None) -> tuple[Path, int] | None:
    """Grava os textos aceitos em db/explicacoes.jsonl (versionado), em ordem estavel.
    A carga (`rodar --recriar`) importa de volta: ninguem precisa gerar de novo."""
    caminho = caminho or config.EXPLICACOES
    if not caminho:
        return None
    linhas = con.execute(f"""SELECT {", ".join(_CAMPOS)} FROM explicacao WHERE status = 'ok'
                             ORDER BY alvo, alvo_id, hash_fatos, provedor, modelo""").fetchall()
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in linhas),
                       encoding="utf-8")
    return caminho, len(linhas)


def importar_cache(con: psycopg.Connection, caminho=None) -> int:
    """Le db/explicacoes.jsonl para a tabela. Texto de fatos antigos fica la sem efeito (o hash nao bate)."""
    caminho = caminho or config.EXPLICACOES
    if not caminho or not Path(caminho).exists():
        return 0
    linhas = [json.loads(x) for x in Path(caminho).read_text(encoding="utf-8").splitlines() if x.strip()]
    con.cursor().executemany(
        """INSERT INTO explicacao (alvo, alvo_id, hash_fatos, provedor, modelo, texto, fatos, tentativas,
           latencia_s, status) VALUES (%(alvo)s, %(alvo_id)s, %(hash_fatos)s, %(provedor)s, %(modelo)s, %(texto)s,
           %(fatos)s, %(tentativas)s, %(latencia_s)s, 'ok')
           ON CONFLICT (alvo, alvo_id, hash_fatos, provedor, modelo) DO NOTHING""", linhas)
    return len(linhas)
