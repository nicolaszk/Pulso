"""Passo 5 do pipeline: tirar os eventos da fila de processamento, um por um, por data.

Para cada evento: marca como processado, reavalia a solicitacao dele com todos os eventos
ja processados (avaliacao.avaliar), atualiza estado_paciente e, se o motor quer outra fila
(ou tirar da fila), abre ou atualiza um pedido em solicitacao_mudanca. A fila oficial nao
muda aqui: so quando um medico aprova (fila.decidir).
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import psycopg

from .. import config
from ..db import Jsonb
from .avaliacao import Avaliacao, avaliar
from .fila import posicao_estimada, renumerar
from priorizacao import config as regras
from priorizacao.limpeza import _hash_conteudo


class EventoInvalido(Exception):
    pass


def data_calculo(data_evento, data_referencia=None) -> date:
    """O motor avalia em max(data de referencia, data do evento): o backlog do CSV e lido
    "hoje"; um evento novo com data posterior avanca o relogio."""
    ref = pd.Timestamp(data_referencia or config.DATA_REFERENCIA).date()
    d = _como_data(data_evento)
    return max(ref, d) if d else ref


def _como_data(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return pd.Timestamp(v).date()


# ---------------------------------------------------------------------------- eventos
def processar_pendentes(con: psycopg.Connection, limite: int | None = None, data_referencia=None) -> dict:
    """Processa os eventos pendentes em ordem (data_evento, id). Devolve as contagens."""
    contagem = {"eventos": 0, "aberta": 0, "atualizada": 0, "obsoleta": 0, "sem_mudanca": 0}
    while limite is None or contagem["eventos"] < limite:
        ev = con.execute("""SELECT id FROM evento_clinico WHERE processado_em IS NULL
                            ORDER BY data_evento, id LIMIT 1""").fetchone()
        if ev is None:
            break
        r = processar_evento(con, ev["id"], data_referencia)
        contagem["eventos"] += 1
        contagem[r["acao"] if r else "sem_mudanca"] += 1
    contagem["pendentes"] = con.execute(
        "SELECT count(*) AS n FROM evento_clinico WHERE processado_em IS NULL").fetchone()["n"]
    return contagem


def processar_ate_pedidos(con: psycopg.Connection, pedidos: int, data_referencia=None) -> dict:
    """Processa eventos em ordem ate a caixa do medico ter `pedidos` pendentes (ou os eventos acabarem).

    Para a demo: a revisao humana comeca com alguns pedidos e o resto dos eventos fica pendente
    para ser processado um a um pela API (POST /eventos/processar).
    """
    contagem = {"eventos": 0, "aberta": 0, "atualizada": 0, "obsoleta": 0, "sem_mudanca": 0}
    while _pedidos_pendentes(con) < pedidos:
        r = processar_pendentes(con, 1, data_referencia)
        if r["eventos"] == 0:
            break
        for k in ("eventos", "aberta", "atualizada", "obsoleta", "sem_mudanca"):
            contagem[k] += r[k]
    contagem["pendentes"] = con.execute(
        "SELECT count(*) AS n FROM evento_clinico WHERE processado_em IS NULL").fetchone()["n"]
    contagem["pedidos_pendentes"] = _pedidos_pendentes(con)
    return contagem


def _pedidos_pendentes(con: psycopg.Connection) -> int:
    return con.execute("SELECT count(*) AS n FROM solicitacao_mudanca WHERE status = 'pendente'").fetchone()["n"]


def processar_evento(con: psycopg.Connection, evento_id: str, data_referencia=None) -> dict | None:
    """Processa um evento (transacao propria). Devolve o que aconteceu com o pedido de mudanca."""
    with con.transaction():
        ev = con.execute("""UPDATE evento_clinico SET processado_em = now()
                            WHERE id = %s AND processado_em IS NULL
                            RETURNING id, solicitacao_id, data_evento""", (evento_id,)).fetchone()
        if ev is None:
            raise EventoInvalido(f"evento {evento_id} nao existe ou ja foi processado")
        return reavaliar(con, ev["solicitacao_id"], data_calculo(ev["data_evento"], data_referencia), ev["id"])


def registrar_evento(con: psycopg.Connection, dados: dict) -> str:
    """Evento novo (API): valida no mesmo dominio da limpeza e entra como pendente."""
    tipo, resultado = dados.get("tipo_evento"), dados.get("resultado")
    if tipo not in regras.TIPOS_EVENTO:
        raise EventoInvalido(f"tipo_evento desconhecido: {tipo}")
    if resultado not in regras.TIPOS_EVENTO[tipo]:
        raise EventoInvalido(f"resultado invalido para {tipo}: {resultado}")
    valor = dados.get("valor_numerico")
    if tipo in ("hba1c", "internacao") and valor is None:
        raise EventoInvalido(f"{tipo} exige valor_numerico")
    if tipo not in ("hba1c", "internacao"):
        valor = None
    data_evento = _como_data(dados.get("data_evento"))
    if data_evento is None or data_evento > date.today():
        raise EventoInvalido("data_evento vazia ou no futuro")
    sid = dados.get("solicitacao_id")
    sol = con.execute("SELECT status, duplicata_de FROM solicitacao WHERE id = %s", (sid,)).fetchone()
    if sol is None:
        raise EventoInvalido(f"solicitacao {sid} nao existe")
    original = None
    if sol["status"] == "duplicata":  # como na limpeza: o evento vai para o mestre
        original, sid = sid, sol["duplicata_de"]
    descricao = (dados.get("descricao") or "").strip()
    hash_ = _hash_conteudo(sid, pd.Timestamp(data_evento), tipo, resultado,
                           float(valor) if valor is not None else None, descricao)
    if con.execute("SELECT 1 FROM evento_clinico WHERE hash_conteudo = %s", (hash_,)).fetchone():
        raise EventoInvalido("evento repetido (mesmo conteudo de um evento ja registrado)")
    with con.transaction():
        novo = con.execute("""SELECT 'EVT-' || lpad((coalesce(max(substr(id, 5)::int), 0) + 1)::text, 6, '0') AS id
                              FROM evento_clinico""").fetchone()["id"]
        con.execute("""INSERT INTO evento_clinico (id, solicitacao_id, data_evento, tipo_evento, resultado,
                       valor_numerico, descricao, origem, solicitacao_id_original, hash_conteudo)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (novo, sid, data_evento, tipo, resultado, valor, descricao,
                     (dados.get("origem") or "api").strip(), original, hash_))
    return novo


# ---------------------------------------------------------------------------- reavaliacao
def varrer(con: psycopg.Connection, data=None) -> dict:
    """Reavalia toda a fila oficial numa data (ex.: diaria): sinais expiram, prazos vencem."""
    data = _como_data(data) or data_calculo(None)
    contagem = {"solicitacoes": 0, "aberta": 0, "atualizada": 0, "obsoleta": 0, "sem_mudanca": 0}
    ids = [r["solicitacao_id"] for r in con.execute(
        "SELECT solicitacao_id FROM fila_priorizada ORDER BY posicao_final").fetchall()]
    for sid in ids:
        with con.transaction():
            r = reavaliar(con, sid, data, None)
        contagem["solicitacoes"] += 1
        contagem[r["acao"] if r else "sem_mudanca"] += 1
    return contagem


def reavaliar(con: psycopg.Connection, solicitacao_id: str, data: date, evento_id: str | None) -> dict | None:
    sol = con.execute("SELECT status, dados_motor FROM solicitacao WHERE id = %s", (solicitacao_id,)).fetchone()
    if sol is None or sol["status"] != "ativa":
        return None  # duplicata ou ja saiu: o evento fica registrado, sem efeito na fila
    eventos = con.execute("""
        SELECT id AS evento_id, data_evento, tipo_evento, resultado, valor_numerico, descricao, origem
        FROM evento_clinico
        WHERE solicitacao_id = %s AND processado_em IS NOT NULL AND data_evento <= %s
        ORDER BY data_evento, id""", (solicitacao_id, data)).fetchall()
    av = avaliar(sol["dados_motor"], eventos, data)
    gravar_estado(con, av, evento_id)
    return reconciliar(con, av, evento_id)


def gravar_estado(con: psycopg.Connection, av: Avaliacao, evento_id: str | None) -> None:
    con.execute("""
        INSERT INTO estado_paciente (solicitacao_id, data_calculo, fila, sair, data_limite_efetiva, n_sinais,
            dor, sem_urgencia, motivos, justificativa, sinais, evidencias, marcacoes, pendencias,
            proxima_revisao, ultimo_evento_id, atualizado_em)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (solicitacao_id) DO UPDATE SET
            data_calculo = EXCLUDED.data_calculo, fila = EXCLUDED.fila, sair = EXCLUDED.sair,
            data_limite_efetiva = EXCLUDED.data_limite_efetiva, n_sinais = EXCLUDED.n_sinais,
            dor = EXCLUDED.dor, sem_urgencia = EXCLUDED.sem_urgencia, motivos = EXCLUDED.motivos,
            justificativa = EXCLUDED.justificativa, sinais = EXCLUDED.sinais,
            evidencias = EXCLUDED.evidencias, marcacoes = EXCLUDED.marcacoes,
            pendencias = EXCLUDED.pendencias, proxima_revisao = EXCLUDED.proxima_revisao,
            ultimo_evento_id = coalesce(EXCLUDED.ultimo_evento_id, estado_paciente.ultimo_evento_id),
            atualizado_em = now()""",
        estado_params(av, evento_id))


def estado_params(av: Avaliacao, evento_id: str | None) -> tuple:
    return (av.solicitacao_id, av.data_calculo, av.fila, av.sair, av.data_limite_efetiva, av.n_sinais,
            av.dor, av.sem_urgencia, Jsonb(av.motivos), av.justificativa, Jsonb(av.sinais),
            Jsonb(av.evidencias), Jsonb(av.marcacoes), Jsonb(av.pendencias), av.proxima_revisao, evento_id)


def _atualizar_na_mesma_fila(con: psycopg.Connection, av: Avaliacao) -> None:
    """Mesma fila: sem pedido. Desempate (sinais, dor), justificativa e marcacoes acompanham
    os eventos; so trocar de fila (ou sair) precisa do medico."""
    mudou = con.execute("""
        UPDATE fila_priorizada SET data_limite_efetiva = %s, n_sinais = %s, dor = %s, justificativa = %s,
               marcacoes = %s, atualizada_em = now()
        WHERE solicitacao_id = %s AND (data_limite_efetiva, n_sinais, coalesce(dor, -1), justificativa, marcacoes)
              IS DISTINCT FROM (%s::date, %s::smallint, coalesce(%s::smallint, -1), %s, %s::jsonb)
        RETURNING 1""",
        (av.data_limite_efetiva, av.n_sinais, av.dor, av.justificativa, Jsonb(av.marcacoes), av.solicitacao_id,
         av.data_limite_efetiva, av.n_sinais, av.dor, av.justificativa, Jsonb(av.marcacoes))).fetchone()
    if mudou:
        renumerar(con)


def reconciliar(con: psycopg.Connection, av: Avaliacao, evento_id: str | None) -> dict | None:
    """Compara o que o motor quer com a fila oficial e cuida do pedido pendente (no maximo um)."""
    sid = av.solicitacao_id
    oficial = con.execute("""SELECT fp.fila, fp.posicao_final, s.data_entrada_fila
                             FROM fila_priorizada fp JOIN solicitacao s ON s.id = fp.solicitacao_id
                             WHERE fp.solicitacao_id = %s""", (sid,)).fetchone()
    if oficial is None:
        return None
    pend = con.execute("""SELECT id, tipo, fila_proposta FROM solicitacao_mudanca
                          WHERE solicitacao_id = %s AND status = 'pendente' FOR UPDATE""", (sid,)).fetchone()

    if av.sair:
        tipo, alvo = "sair", None
    elif av.fila == oficial["fila"]:
        _atualizar_na_mesma_fila(con, av)
        if pend:
            con.execute("""UPDATE solicitacao_mudanca SET status = 'obsoleta', atualizada_em = now()
                           WHERE id = %s""", (pend["id"],))
            return {"acao": "obsoleta", "mudanca_id": pend["id"], "solicitacao_id": sid}
        return None
    else:
        alvo = av.fila
        tipo = "subir" if regras.ORDEM_FILA[alvo] < regras.ORDEM_FILA[oficial["fila"]] else "descer"
    if tipo == "descer" and av.oncologico:  # regra de ouro: nunca rebaixar CID C*
        return None

    if tipo == "sair":
        motivo = f"sair da fila: {av.evidencia_saida}"
        evidencias = [{"evento_id": e} for e in av.eventos_saida]
        pos_proposta = None
    else:
        motivo = (f"{tipo} de {oficial['fila']} ({regras.NOME_FILA[oficial['fila']]}) para "
                  f"{alvo} ({regras.NOME_FILA[alvo]}): {av.motivo_texto or ', '.join(av.motivos)}")
        evidencias = av.evidencias_motivo
        pos_proposta = posicao_estimada(con, sid, av.ordem_fila, av.data_limite_efetiva, av.n_sinais,
                                        av.dor, oficial["data_entrada_fila"])
    valores = {"motivo": motivo, "evidencias": Jsonb(evidencias), "proposta": Jsonb(av.proposta()),
               "evento_id": evento_id, "data": av.data_calculo, "pos_atual": oficial["posicao_final"],
               "pos_proposta": pos_proposta}

    if pend and pend["tipo"] == tipo and pend["fila_proposta"] == alvo:
        con.execute("""UPDATE solicitacao_mudanca SET motivo = %(motivo)s, evidencias = %(evidencias)s,
                       proposta = %(proposta)s,
                       data_referencia = %(data)s, posicao_atual = %(pos_atual)s,
                       posicao_proposta = %(pos_proposta)s, atualizada_em = now()
                       WHERE id = %(id)s""", {**valores, "id": pend["id"]})
        return {"acao": "atualizada", "mudanca_id": pend["id"], "solicitacao_id": sid, "tipo": tipo}
    if pend:
        con.execute("""UPDATE solicitacao_mudanca SET status = 'substituida', atualizada_em = now()
                       WHERE id = %s""", (pend["id"],))
    novo = con.execute("""
        INSERT INTO solicitacao_mudanca (solicitacao_id, tipo, oncologico, fila_atual, fila_proposta,
            posicao_atual, posicao_proposta, motivo, evidencias, proposta, evento_id, data_referencia)
        VALUES (%(sid)s, %(tipo)s, %(onco)s, %(fila_atual)s, %(alvo)s, %(pos_atual)s, %(pos_proposta)s,
                %(motivo)s, %(evidencias)s, %(proposta)s, %(evento_id)s, %(data)s)
        RETURNING id""", {**valores, "sid": sid, "tipo": tipo, "onco": av.oncologico,
                          "fila_atual": oficial["fila"], "alvo": alvo}).fetchone()["id"]
    return {"acao": "aberta", "mudanca_id": novo, "solicitacao_id": sid, "tipo": tipo,
            "substituiu": pend["id"] if pend else None}
