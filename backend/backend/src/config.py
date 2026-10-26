"""Configuracao do backend: caminhos, banco e data de referencia.

Valores vem do ambiente ou de backend/.env (copie de .env.example).
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
RAIZ = BACKEND.parent


def _carregar_env(arquivo: Path) -> None:
    if not arquivo.exists():
        return
    for linha in arquivo.read_text().splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


_carregar_env(BACKEND / ".env")
_carregar_env(RAIZ / ".env")  # chaves de LLM que o time ja guarda na raiz (git-ignored)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pulso:pulso@localhost:5432/pulso")
DATASET = Path(os.getenv("PULSO_DATASET", RAIZ / "ideas" / "data" / "dataset"))
# "Hoje" do dataset. Eventos sao avaliados em max(data de referencia, data do evento).
DATA_REFERENCIA = os.getenv("PULSO_DATA_REFERENCIA", "2026-10-23")
SCHEMA = RAIZ / "db" / "schema.sql"
# Textos do LLM ja gerados (versionado): a carga importa, `explicar` grava. Vazio = desligado.
EXPLICACOES = os.getenv("PULSO_EXPLICACOES", str(RAIZ / "db" / "explicacoes.jsonl")) or None

# Codigo dos colegas que o pipeline usa sem copiar:
#   fila_cirurgica/priorizacao   motor (limpeza, sinais, triagem, classificadores)
#   ideas/data/build_features.py features por paciente
#   db/gerar_seed.py             medicos e hospitais sinteticos
for _p in (RAIZ / "fila_cirurgica", RAIZ / "ideas" / "data", RAIZ / "db"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
