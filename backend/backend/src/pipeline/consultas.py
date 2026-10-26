"""Leituras usadas pela CLI e pela API: fila, caixa de pedidos, detalhe, resumo e o CSV."""
from __future__ import annotations

import csv
import io
from pathlib import Path

import psycopg

from .fila import RegraDeOuroViolada, conferir_regra_de_ouro


# Dados do paciente e do procedimento que as telas mostram junto de cada solicitacao
_COLUNAS_PACIENTE = """pa.id AS paciente_id, pa.nome AS paciente_nome, pa.idade, pa.municipio,
                       pr.nome AS procedimento, es.nome AS especialidade, s.data_entrada_fila,
                       DATE '2026-10-23' - s.data_entrada_fila AS dias_em_fila, s.prioridade_regulacao"""
_JOIN_PACIENTE = """JOIN paciente pa ON pa.id = s.paciente_id
                    JOIN procedimento pr ON pr.id = s.procedimento_id
                    JOIN especialidade es ON es.id = pr.especialidade_id"""


def fila(con: psycopg.Connection, modo: str = "oficial", grupo: str | None = None,
         limite: int = 100, offset: int = 0) -> list[dict]:
    if modo == "oficial":
        sql = f"""SELECT fp.posicao_final AS posicao, fp.solicitacao_id, fp.fila, fp.posicao_fila,
                        fp.data_limite_efetiva, fp.posicao_inicial, fp.justificativa,
                        s.cid_principal, s.cid_principal LIKE 'C%%' AS oncologico,
                        m.id AS mudanca_pendente, m.tipo AS mudanca_tipo, m.fila_proposta, {_COLUNAS_PACIENTE}
                 FROM fila_priorizada fp
                 JOIN solicitacao s ON s.id = fp.solicitacao_id
                 {_JOIN_PACIENTE}
                 LEFT JOIN solicitacao_mudanca m ON m.solicitacao_id = fp.solicitacao_id AND m.status = 'pendente'
                 WHERE %(grupo)s::text IS NULL OR fp.fila = %(grupo)s
                 ORDER BY fp.posicao_final LIMIT %(limite)s OFFSET %(offset)s"""
    elif modo == "recomendada":
        sql = f"""SELECT r.posicao, r.solicitacao_id, r.fila, r.data_limite_efetiva, r.justificativa,
                        r.oncologico, fp.posicao_final AS posicao_oficial, fp.fila AS fila_oficial,
                        s.cid_principal, {_COLUNAS_PACIENTE}
                 FROM fila_recomendada r
                 JOIN solicitacao s ON s.id = r.solicitacao_id
                 {_JOIN_PACIENTE}
                 LEFT JOIN fila_priorizada fp ON fp.solicitacao_id = r.solicitacao_id
                 WHERE %(grupo)s::text IS NULL OR r.fila = %(grupo)s
                 ORDER BY r.posicao LIMIT %(limite)s OFFSET %(offset)s"""
    else:
        raise ValueError("modo deve ser oficial ou recomendada")
    return con.execute(sql, {"grupo": grupo, "limite": limite, "offset": offset}).fetchall()


def mudancas(con: psycopg.Connection, status: str | None = "pendente", limite: int = 100,
             offset: int = 0) -> list[dict]:
    """Caixa do medico: o destino mais urgente primeiro; saidas por ultimo."""
    return con.execute("""
        SELECT m.id, m.solicitacao_id, m.tipo, m.status, m.fila_atual, m.fila_proposta,
               fp.posicao_final AS posicao_atual, m.posicao_proposta,
               -- posicao_proposta e "se so este pedido for aprovado" (gravada no evento); varios pedidos podem
               -- cair na mesma. Esta e a posicao na fila recomendada de agora (todos aprovados), unica.
               CASE WHEN m.status = 'pendente' THEN fr.posicao END AS posicao_recomendada,
               m.motivo, m.evidencias,
               m.evento_id, m.oncologico, m.criada_em, m.atualizada_em, m.medico_id, m.decidida_em,
               m.motivo_decisao, pa.nome AS paciente_nome, pr.nome AS procedimento, md.nome AS medico_nome
        FROM solicitacao_mudanca m
        JOIN solicitacao s ON s.id = m.solicitacao_id
        JOIN paciente pa ON pa.id = s.paciente_id
        JOIN procedimento pr ON pr.id = s.procedimento_id
        LEFT JOIN medico md ON md.id = m.medico_id
        LEFT JOIN fila_grupo g ON g.codigo = m.fila_proposta
        LEFT JOIN fila_priorizada fp ON fp.solicitacao_id = m.solicitacao_id
        LEFT JOIN fila_recomendada fr ON fr.solicitacao_id = m.solicitacao_id
        WHERE %(status)s::text IS NULL OR m.status = %(status)s
        ORDER BY coalesce(g.ordem, 99), m.posicao_proposta NULLS LAST, m.id
        LIMIT %(limite)s OFFSET %(offset)s""", {"status": status, "limite": limite, "offset": offset}).fetchall()


def mudanca(con: psycopg.Connection, mudanca_id: int) -> dict | None:
    return con.execute("SELECT * FROM solicitacao_mudanca WHERE id = %s", (mudanca_id,)).fetchone()


def solicitacao(con: psycopg.Connection, solicitacao_id: str) -> dict | None:
    s = con.execute("""SELECT s.id, s.paciente_id, s.procedimento_id, p.nome AS procedimento, s.cid_principal,
                              s.cid_descricao, s.intensidade_dor_eva, s.limitacao_funcional,
                              s.justificativa_clinica, s.observacoes, s.data_entrada_fila,
                              s.prioridade_regulacao, s.status, s.duplicata_de, s.motivo_status
                       FROM solicitacao s JOIN procedimento p ON p.id = s.procedimento_id
                       WHERE s.id = %s""", (solicitacao_id,)).fetchone()
    if s is None:
        return None
    s["fila_oficial"] = con.execute("""SELECT posicao_final AS posicao, posicao_inicial, fila, posicao_fila,
                                       data_limite_efetiva, justificativa, marcacoes
                                       FROM fila_priorizada WHERE solicitacao_id = %s""",
                                    (solicitacao_id,)).fetchone()
    s["estado_motor"] = con.execute("SELECT * FROM estado_paciente WHERE solicitacao_id = %s",
                                    (solicitacao_id,)).fetchone()
    s["eventos"] = con.execute("""SELECT id, data_evento, tipo_evento, resultado, valor_numerico, descricao,
                                  origem, processado_em FROM evento_clinico WHERE solicitacao_id = %s
                                  ORDER BY data_evento, id""", (solicitacao_id,)).fetchall()
    s["mudancas"] = con.execute("""SELECT m.id, m.tipo, m.status, m.fila_atual, m.fila_proposta, m.motivo,
                                   m.evidencias, m.evento_id, m.criada_em, m.medico_id, md.nome AS medico_nome,
                                   m.decidida_em, m.motivo_decisao
                                   FROM solicitacao_mudanca m LEFT JOIN medico md ON md.id = m.medico_id
                                   WHERE m.solicitacao_id = %s ORDER BY m.id""",
                                (solicitacao_id,)).fetchall()
    s["paciente"] = con.execute("""SELECT pa.id, pa.nome, pa.sexo, pa.idade, pa.municipio, pa.uf,
                                   pa.distancia_hospital_km, pa.comorbidades
                                   FROM paciente pa JOIN solicitacao s ON s.paciente_id = pa.id
                                   WHERE s.id = %s""", (solicitacao_id,)).fetchone()
    s["especialidade"] = con.execute("""SELECT es.nome FROM procedimento pr
                                        JOIN especialidade es ON es.id = pr.especialidade_id
                                        WHERE pr.id = %s""", (s["procedimento_id"],)).fetchone()["nome"]
    s["historico"] = con.execute("""SELECT h.mudanca_id, h.acao, h.de_fila, h.para_fila, h.de_posicao,
                                    h.para_posicao, h.registrado_em, md.nome AS medico_nome
                                    FROM fila_historico h JOIN medico md ON md.id = h.medico_id
                                    WHERE h.solicitacao_id = %s ORDER BY h.id""", (solicitacao_id,)).fetchall()
    f = con.execute("SELECT features FROM features_paciente WHERE solicitacao_id = %s", (solicitacao_id,)).fetchone()
    s["features"] = f["features"] if f else None
    return s


def resumo(con: psycopg.Connection) -> dict:
    r = {}
    r["solicitacoes"] = {x["status"]: x["n"] for x in con.execute(
        "SELECT status, count(*) AS n FROM solicitacao GROUP BY 1 ORDER BY 1").fetchall()}
    r["eventos"] = con.execute("""SELECT count(*) FILTER (WHERE processado_em IS NOT NULL) AS processados,
                                         count(*) FILTER (WHERE processado_em IS NULL) AS pendentes
                                  FROM evento_clinico""").fetchone()
    r["eventos"]["quarentena"] = con.execute("SELECT count(*) AS n FROM evento_quarentena").fetchone()["n"]
    tamanhos = con.execute("""
        SELECT g.codigo, g.nome,
               (SELECT count(*) FROM fila_priorizada fp WHERE fp.fila = g.codigo) AS oficial,
               (SELECT count(*) FROM fila_recomendada fr WHERE fr.fila = g.codigo) AS recomendada
        FROM fila_grupo g ORDER BY g.ordem""").fetchall()
    r["filas"] = tamanhos
    r["mudancas"] = {f"{x['tipo']}/{x['status']}": x["n"] for x in con.execute(
        "SELECT tipo, status, count(*) AS n FROM solicitacao_mudanca GROUP BY 1, 2 ORDER BY 1, 2").fetchall()}
    r["prazo_estourado"] = con.execute("""SELECT count(*) AS n FROM fila_priorizada
                                          WHERE data_limite_efetiva < DATE '2026-10-23'""").fetchone()["n"]
    r["pendencias"] = con.execute("""SELECT count(*) AS n FROM estado_paciente e
                                     JOIN fila_priorizada fp ON fp.solicitacao_id = e.solicitacao_id
                                     WHERE jsonb_array_length(e.pendencias) > 0""").fetchone()["n"]
    r["regra_de_ouro"] = {}
    for tabela in ("fila_priorizada", "fila_recomendada"):
        try:
            r["regra_de_ouro"][tabela] = conferir_regra_de_ouro(con, tabela)
        except RegraDeOuroViolada as exc:
            r["regra_de_ouro"][tabela] = {"ok": False, "erro": str(exc)}
    return r


def pendencias(con: psycopg.Connection) -> list[dict]:
    """Pendencias operacionais (contato, faltas, HbA1c, saidas a confirmar) das solicitacoes na fila oficial."""
    return con.execute("""
        SELECT e.solicitacao_id, pa.nome AS paciente_nome, fp.fila, fp.posicao_final AS posicao, e.pendencias
        FROM estado_paciente e
        JOIN fila_priorizada fp ON fp.solicitacao_id = e.solicitacao_id
        JOIN solicitacao s ON s.id = e.solicitacao_id
        JOIN paciente pa ON pa.id = s.paciente_id
        WHERE jsonb_array_length(e.pendencias) > 0
        ORDER BY fp.posicao_final""").fetchall()


def marcacoes(con: psycopg.Connection, severidade: str | None = None) -> list[dict]:
    """Uma linha por marcacao do motor (dados que pedem olho humano), mais severas primeiro."""
    return con.execute("""
        SELECT e.solicitacao_id, pa.nome AS paciente_nome, fp.fila, fp.posicao_final AS posicao,
               mk->>'marcacao' AS marcacao, mk->>'severidade' AS severidade
        FROM estado_paciente e
        JOIN fila_priorizada fp ON fp.solicitacao_id = e.solicitacao_id
        JOIN solicitacao s ON s.id = e.solicitacao_id
        JOIN paciente pa ON pa.id = s.paciente_id
        CROSS JOIN LATERAL jsonb_array_elements(e.marcacoes) mk
        WHERE %(sev)s::text IS NULL OR mk->>'severidade' = %(sev)s
        ORDER BY array_position(ARRAY['alta', 'media', 'baixa', 'informativa'], mk->>'severidade'),
                 fp.posicao_final""", {"sev": severidade}).fetchall()


def dados(con: psycopg.Connection) -> dict:
    """O que a carga corrigiu, descartou e registrou."""
    return {
        "execucoes": con.execute("""SELECT id, tipo, data_referencia, regras_versao, relatorio, iniciada_em,
                                    terminada_em FROM execucao ORDER BY id""").fetchall(),
        "quarentena": con.execute("""SELECT evento_id, motivo, registro->>'solicitacao_id' AS solicitacao_id,
                                     registro->>'tipo_evento' AS tipo_evento, registro->>'data_evento' AS data_evento
                                     FROM evento_quarentena ORDER BY id""").fetchall(),
        "fora_da_fila": con.execute("""SELECT s.id AS solicitacao_id, pa.nome AS paciente_nome, s.status,
                                       s.duplicata_de, s.motivo_status
                                       FROM solicitacao s JOIN paciente pa ON pa.id = s.paciente_id
                                       WHERE s.status <> 'ativa' ORDER BY s.status, s.id""").fetchall(),
    }


def csv_fila(con: psycopg.Connection, modo: str = "recomendada", com_explicacao: bool = False) -> str:
    """O entregavel: solicitacao_id, posicao, justificativa. com_explicacao: usa o texto do LLM ja
    gerado para os fatos de agora, onde houver (o resto fica com o template)."""
    if modo == "oficial":
        linhas = con.execute("""SELECT solicitacao_id, posicao_final AS posicao, justificativa
                                FROM fila_priorizada ORDER BY posicao_final""").fetchall()
    elif modo == "recomendada":
        linhas = con.execute("SELECT solicitacao_id, posicao, justificativa FROM fila_recomendada ORDER BY posicao").fetchall()
    else:
        raise ValueError("modo deve ser oficial ou recomendada")
    if com_explicacao:
        from .explicacao import em_cache
        for x in linhas:
            x["justificativa"] = em_cache(con, "solicitacao", x["solicitacao_id"]) or x["justificativa"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["solicitacao_id", "posicao", "justificativa"])
    w.writerows([[x["solicitacao_id"], x["posicao"], x["justificativa"]] for x in linhas])
    return buf.getvalue()


def exportar(con: psycopg.Connection, caminho, modo: str = "recomendada", com_explicacao: bool = False) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(csv_fila(con, modo, com_explicacao), encoding="utf-8")
    return caminho
