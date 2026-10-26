"""Conexao com o Postgres e aplicacao do schema (db/schema.sql)."""
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import config

__all__ = ["conectar", "aplicar_schema", "banco_populado", "Jsonb"]


def conectar(url: str | None = None, autocommit: bool = True) -> psycopg.Connection:
    """autocommit=True: cada `with con.transaction()` e uma transacao de verdade."""
    return psycopg.connect(url or config.DATABASE_URL, row_factory=dict_row, autocommit=autocommit)


def aplicar_schema(con: psycopg.Connection) -> None:
    """Apaga e recria todas as tabelas."""
    con.execute(config.SCHEMA.read_text())


def banco_populado(con: psycopg.Connection) -> bool:
    existe = con.execute("SELECT to_regclass('solicitacao') IS NOT NULL AS ok").fetchone()["ok"]
    return existe and con.execute("SELECT EXISTS (SELECT 1 FROM solicitacao) AS ok").fetchone()["ok"]
