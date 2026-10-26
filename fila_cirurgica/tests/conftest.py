import sys
from pathlib import Path

# torna o pacote `priorizacao` importavel rodando pytest de qualquer lugar
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DATASET = RAIZ.parent / "ideas" / "data" / "dataset"
