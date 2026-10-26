# -*- coding: utf-8 -*-
"""Banco SQLite: esquema (registro imutavel + versoes da fila) e gravacao.

A carga inicial grava tudo numa transacao unica: ou entra a versao 1 inteira,
ou nada.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS regras_versao (versao TEXT PRIMARY KEY, criada_em TEXT, config_json TEXT);
CREATE TABLE IF NOT EXISTS execucao (id INTEGER PRIMARY KEY, tipo TEXT, data_referencia TEXT,
  regras_versao TEXT, hashes_json TEXT, iniciada_em TEXT, terminada_em TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS solicitacao (solicitacao_id TEXT PRIMARY KEY, paciente_id TEXT, mestre_id TEXT,
  status TEXT CHECK (status IN ('ativa','duplicata','saiu')), dados_json TEXT, evidencia_saida TEXT);
CREATE TABLE IF NOT EXISTS evento (evento_id TEXT PRIMARY KEY, solicitacao_id TEXT, paciente_id TEXT,
  data_evento TEXT, data_recebimento TEXT, tipo TEXT, resultado TEXT, valor REAL,
  descricao TEXT, origem TEXT, hash_conteudo TEXT UNIQUE, execucao_id INTEGER);
CREATE TABLE IF NOT EXISTS quarentena (id INTEGER PRIMARY KEY, origem TEXT, registro_json TEXT,
  motivo TEXT, recebido_em TEXT, execucao_id INTEGER, resolvido INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS estado (solicitacao_id TEXT PRIMARY KEY, sinais_json TEXT, evidencias_json TEXT,
  hash_entrada TEXT, atualizado_em TEXT);
CREATE TABLE IF NOT EXISTS fila_versao (versao_id INTEGER PRIMARY KEY, execucao_id INTEGER,
  data_referencia TEXT, regras_versao TEXT, criada_em TEXT, n_ativas INTEGER);
CREATE TABLE IF NOT EXISTS fila_item (versao_id INTEGER, solicitacao_id TEXT, fila TEXT, ordem_fila INTEGER,
  data_limite_efetiva TEXT, posicao INTEGER, posicao_fila INTEGER, classificador TEXT,
  classificador_versao TEXT, componentes_json TEXT, rotulos_json TEXT, marcacoes_json TEXT,
  pendencias_json TEXT, proxima_revisao TEXT, justificativa TEXT,
  PRIMARY KEY (versao_id, solicitacao_id));
CREATE INDEX IF NOT EXISTS ix_fila_ordem ON fila_item (versao_id, ordem_fila, data_limite_efetiva);
CREATE INDEX IF NOT EXISTS ix_revisao ON fila_item (versao_id, proxima_revisao);
CREATE TABLE IF NOT EXISTS mudanca (id INTEGER PRIMARY KEY, solicitacao_id TEXT, de_fila TEXT, para_fila TEXT,
  ajuste_dias INTEGER, autor TEXT, motivo TEXT, evidencia_json TEXT, status TEXT,
  validade TEXT, criada_em TEXT);
CREATE TABLE IF NOT EXISTS decisao_regulador (id INTEGER PRIMARY KEY, mudanca_id INTEGER, decisao TEXT,
  regulador TEXT, motivo TEXT, decidida_em TEXT);
"""


def conectar(caminho) -> sqlite3.Connection:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(caminho))
    con.execute("PRAGMA foreign_keys = ON")
    return con


def criar_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)
    con.commit()


def ja_populado(con: sqlite3.Connection) -> bool:
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fila_versao'")
    if cur.fetchone() is None:
        return False
    return con.execute("SELECT COUNT(*) FROM fila_versao").fetchone()[0] > 0


def recriar(caminho) -> None:
    p = Path(caminho)
    if p.exists():
        p.unlink()


def gravar_carga_inicial(con, *, execucao, regras, solicitacoes, eventos, quarentena,
                         estados, itens, n_ativas) -> int:
    """Grava a versao 1 inteira numa transacao unica. Devolve o versao_id."""
    j = lambda o: json.dumps(o, ensure_ascii=False, sort_keys=True, default=str)
    try:
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO regras_versao (versao, criada_em, config_json) VALUES (?,?,?)",
                    (regras["versao"], execucao["iniciada_em"], j(regras["config"])))
        cur.execute("""INSERT INTO execucao (tipo, data_referencia, regras_versao, hashes_json,
                       iniciada_em, terminada_em, status) VALUES (?,?,?,?,?,?,?)""",
                    (execucao["tipo"], execucao["data_referencia"], regras["versao"],
                     j(execucao["hashes"]), execucao["iniciada_em"], execucao["terminada_em"], "ok"))
        exec_id = cur.lastrowid

        cur.executemany("""INSERT OR REPLACE INTO solicitacao
                        (solicitacao_id, paciente_id, mestre_id, status, dados_json, evidencia_saida)
                        VALUES (?,?,?,?,?,?)""",
                        [(s["solicitacao_id"], s["paciente_id"], s["mestre_id"], s["status"],
                          j(s["dados"]), s.get("evidencia_saida")) for s in solicitacoes])

        cur.executemany("""INSERT OR IGNORE INTO evento
                        (evento_id, solicitacao_id, paciente_id, data_evento, data_recebimento, tipo,
                         resultado, valor, descricao, origem, hash_conteudo, execucao_id)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [(e["evento_id"], e["solicitacao_id"], e["paciente_id"], e["data_evento"],
                          e["data_recebimento"], e["tipo"], e["resultado"], e["valor"], e["descricao"],
                          e["origem"], e["hash_conteudo"], exec_id) for e in eventos])

        cur.executemany("""INSERT INTO quarentena (origem, registro_json, motivo, recebido_em, execucao_id)
                        VALUES (?,?,?,?,?)""",
                        [(q["origem"], q["registro_json"], q["motivo"], execucao["data_referencia"], exec_id)
                         for q in quarentena])

        cur.executemany("""INSERT OR REPLACE INTO estado
                        (solicitacao_id, sinais_json, evidencias_json, hash_entrada, atualizado_em)
                        VALUES (?,?,?,?,?)""",
                        [(st["solicitacao_id"], j(st["sinais"]), j(st["evidencias"]),
                          st["hash_entrada"], execucao["terminada_em"]) for st in estados])

        cur.execute("""INSERT INTO fila_versao (execucao_id, data_referencia, regras_versao, criada_em, n_ativas)
                    VALUES (?,?,?,?,?)""",
                    (exec_id, execucao["data_referencia"], regras["versao"], execucao["terminada_em"], n_ativas))
        versao_id = cur.lastrowid

        cur.executemany("""INSERT INTO fila_item
                        (versao_id, solicitacao_id, fila, ordem_fila, data_limite_efetiva, posicao,
                         posicao_fila, classificador, classificador_versao, componentes_json, rotulos_json,
                         marcacoes_json, pendencias_json, proxima_revisao, justificativa)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [(versao_id, it["solicitacao_id"], it["fila"], it["ordem_fila"],
                          it["data_limite_efetiva"], it["posicao"], it["posicao_fila"], it["classificador"],
                          it["classificador_versao"], j(it["componentes"]), j(it["rotulos"]),
                          j(it["marcacoes"]), j(it["pendencias"]), it["proxima_revisao"], it["justificativa"])
                         for it in itens])
        con.commit()
        return versao_id
    except Exception:
        con.rollback()
        raise
