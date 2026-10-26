"""Testes do pipeline num banco separado (pulso_teste), criado se nao existir.
Precisa do Postgres do docker-compose.yml; sem ele os testes sao pulados."""
import os

import psycopg
import pytest

URL_TESTE = os.getenv("DATABASE_URL_TESTE", "postgresql://pulso:pulso@localhost:5432/pulso_teste")
os.environ["DATABASE_URL"] = URL_TESTE  # antes de importar src.config
os.environ["PULSO_EXPLICACOES"] = ""  # a carga dos testes nao importa db/explicacoes.jsonl

from src import db  # noqa: E402
from src.pipeline import carga, processamento  # noqa: E402


def _criar_banco_teste() -> None:
    base, nome = URL_TESTE.rsplit("/", 1)
    with psycopg.connect(f"{base}/postgres", autocommit=True) as con:
        if not con.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nome,)).fetchone():
            con.execute(f'CREATE DATABASE "{nome}"')


def carregar_tudo() -> dict:
    with db.conectar() as con:
        r = carga.carregar(con, recriar=True)
        r["processamento"] = processamento.processar_pendentes(con)
    return r


@pytest.fixture(scope="session")
def banco():
    """Banco carregado e com todos os eventos processados (passos 1-5)."""
    try:
        _criar_banco_teste()
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres indisponivel ({exc}); rode: docker compose up -d db")
    return carregar_tudo()


@pytest.fixture
def con(banco):
    """Conexao sem autocommit: tudo o que o teste muda e desfeito no fim."""
    c = db.conectar(autocommit=False)
    yield c
    c.rollback()
    c.close()
