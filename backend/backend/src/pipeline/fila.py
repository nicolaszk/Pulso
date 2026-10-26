"""Fila oficial (fila_priorizada): ordem, regra de ouro e decisao do medico.

A fila oficial so muda quando um medico aprova uma solicitacao_mudanca. Toda aprovacao
renumera as posicoes, confere a regra de ouro e grava o historico, numa transacao so:
se a regra de ouro falhar, nada muda.
"""
from __future__ import annotations

import psycopg

from ..db import Jsonb

# Mesma chave de priorizacao/saida.py: fila, data limite, mais sinais, mais dor, entrada, id
ORDEM_SQL = """g.ordem, fp.data_limite_efetiva, fp.n_sinais DESC, coalesce(fp.dor, -1) DESC,
               s.data_entrada_fila, fp.solicitacao_id COLLATE "C" """


class RegraDeOuroViolada(Exception):
    pass


class DecisaoInvalida(Exception):
    pass


def renumerar(con: psycopg.Connection) -> None:
    con.execute(f"""
        WITH ordem AS (
            SELECT fp.solicitacao_id,
                   row_number() OVER (ORDER BY {ORDEM_SQL}) AS pos,
                   row_number() OVER (PARTITION BY fp.fila ORDER BY {ORDEM_SQL}) AS pos_fila
            FROM fila_priorizada fp
            JOIN fila_grupo g ON g.codigo = fp.fila
            JOIN solicitacao s ON s.id = fp.solicitacao_id)
        UPDATE fila_priorizada fp SET posicao_final = o.pos, posicao_fila = o.pos_fila
        FROM ordem o
        WHERE o.solicitacao_id = fp.solicitacao_id
          AND (fp.posicao_final IS DISTINCT FROM o.pos OR fp.posicao_fila IS DISTINCT FROM o.pos_fila)""")


def conferir_regra_de_ouro(con: psycopg.Connection, tabela: str = "fila_priorizada") -> dict:
    """Nenhum CID C* abaixo de um paciente sem urgencia clinica (definicao do motor, com
    todos os eventos ja processados). Levanta RegraDeOuroViolada se falhar."""
    pos = "posicao_final" if tabela == "fila_priorizada" else "posicao"
    r = con.execute(f"""
        SELECT max(f.{pos}) FILTER (WHERE s.cid_principal LIKE 'C%') AS ultimo_oncologico,
               min(f.{pos}) FILTER (WHERE e.sem_urgencia)             AS primeiro_sem_urgencia
        FROM {tabela} f
        JOIN solicitacao s ON s.id = f.solicitacao_id
        JOIN estado_paciente e ON e.solicitacao_id = f.solicitacao_id""").fetchone()
    ok = r["ultimo_oncologico"] is None or r["primeiro_sem_urgencia"] is None \
        or r["ultimo_oncologico"] < r["primeiro_sem_urgencia"]
    if not ok:
        raise RegraDeOuroViolada(f"{tabela}: oncologico na posicao {r['ultimo_oncologico']}, "
                                 f"primeiro sem urgencia na {r['primeiro_sem_urgencia']}")
    return {**r, "ok": True}


def posicao_estimada(con: psycopg.Connection, solicitacao_id: str, ordem_fila: int, data_limite: str,
                     n_sinais: int, dor: int | None, data_entrada) -> int:
    """Onde a solicitacao ficaria na fila oficial de agora com esses valores."""
    return con.execute(f"""
        SELECT count(*) + 1 AS pos
        FROM fila_priorizada fp
        JOIN fila_grupo g ON g.codigo = fp.fila
        JOIN solicitacao s ON s.id = fp.solicitacao_id
        WHERE fp.solicitacao_id <> %(sid)s
          AND (g.ordem, fp.data_limite_efetiva, -fp.n_sinais, -coalesce(fp.dor, -1),
               s.data_entrada_fila, fp.solicitacao_id COLLATE "C")
            < (%(ordem)s, %(limite)s::date, -%(n)s, -coalesce(%(dor)s::smallint, -1),
               %(entrada)s::date, %(sid)s COLLATE "C")""",
        {"sid": solicitacao_id, "ordem": ordem_fila, "limite": data_limite, "n": n_sinais,
         "dor": dor, "entrada": data_entrada}).fetchone()["pos"]


def decidir(con: psycopg.Connection, mudanca_id: int, aprovar: bool, medico_id: int,
            motivo: str | None = None) -> dict:
    """Aprova ou rejeita um pedido pendente. Rejeitar exige motivo escrito."""
    motivo = (motivo or "").strip() or None
    with con.transaction():
        m = con.execute("SELECT * FROM solicitacao_mudanca WHERE id = %s FOR UPDATE", (mudanca_id,)).fetchone()
        if m is None:
            raise DecisaoInvalida(f"pedido {mudanca_id} nao existe")
        if m["status"] != "pendente":
            raise DecisaoInvalida(f"pedido {mudanca_id} ja esta {m['status']}")
        if con.execute("SELECT 1 FROM medico WHERE id = %s", (medico_id,)).fetchone() is None:
            raise DecisaoInvalida(f"medico {medico_id} nao existe")
        if not aprovar:
            if not motivo:
                raise DecisaoInvalida("rejeitar exige um motivo escrito")
            con.execute("""UPDATE solicitacao_mudanca SET status = 'rejeitada', medico_id = %s,
                           decidida_em = now(), motivo_decisao = %s WHERE id = %s""",
                        (medico_id, motivo, mudanca_id))
            return {"mudanca_id": mudanca_id, "status": "rejeitada"}

        sid = m["solicitacao_id"]
        antes = con.execute("SELECT fila, posicao_final FROM fila_priorizada WHERE solicitacao_id = %s",
                            (sid,)).fetchone()
        if m["tipo"] == "sair":
            con.execute("DELETE FROM fila_priorizada WHERE solicitacao_id = %s", (sid,))
            con.execute("UPDATE solicitacao SET status = 'saiu', motivo_status = %s WHERE id = %s",
                        (m["motivo"], sid))
        else:
            p = m["proposta"]
            con.execute("""UPDATE fila_priorizada SET fila = %s, data_limite_efetiva = %s, n_sinais = %s,
                           dor = %s, justificativa = %s, marcacoes = %s, classe_swalis = %s,
                           atualizada_em = now() WHERE solicitacao_id = %s""",
                        (p["fila"], p["data_limite_efetiva"], p["n_sinais"], p["dor"], p["justificativa"],
                         Jsonb(p["marcacoes"]), p["classe_swalis"], sid))
        renumerar(con)
        conferir_regra_de_ouro(con)
        depois = con.execute("SELECT fila, posicao_final FROM fila_priorizada WHERE solicitacao_id = %s",
                             (sid,)).fetchone()
        con.execute("""INSERT INTO fila_historico (solicitacao_id, mudanca_id, acao, de_fila, para_fila,
                       de_posicao, para_posicao, medico_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (sid, mudanca_id, "saida" if m["tipo"] == "sair" else "mudanca", antes["fila"],
                     depois["fila"] if depois else None, antes["posicao_final"],
                     depois["posicao_final"] if depois else None, medico_id))
        con.execute("""UPDATE solicitacao_mudanca SET status = 'aprovada', medico_id = %s,
                       decidida_em = now(), motivo_decisao = %s WHERE id = %s""",
                    (medico_id, motivo, mudanca_id))
        return {"mudanca_id": mudanca_id, "status": "aprovada", "solicitacao_id": sid,
                "de": dict(antes), "para": dict(depois) if depois else None}
