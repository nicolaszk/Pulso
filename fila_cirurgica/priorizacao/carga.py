# -*- coding: utf-8 -*-
"""Passo 1 - Carga.

Le os tres CSVs exatamente como vieram, sem corrigir nada (toda correcao e do
passo 2), e calcula o hash SHA-256 de cada arquivo para o registro de execucao.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ARQUIVOS = {
    "fila": "fila_cirurgica.csv",
    "eventos": "eventos_clinicos.csv",
    "procedimentos": "procedimentos.csv",
}

# Colunas minimas que, se faltarem, param a carga nomeando arquivo e coluna.
COLUNAS_OBRIGATORIAS = {
    "fila": ["solicitacao_id", "paciente_id", "procedimento_id", "cid_principal", "data_entrada_fila"],
    "eventos": ["evento_id", "solicitacao_id", "paciente_id", "data_evento", "tipo_evento", "resultado"],
    "procedimentos": ["procedimento_id"],
}

# Datas convertidas com coerce; data invalida vira NaT e e tratada no passo 2.
DATAS = {
    "fila": ["data_entrada_fila", "data_ultima_revisao_prioridade", "data_hba1c_ultima"],
    "eventos": ["data_evento"],
    "procedimentos": [],
}


@dataclass
class Brutos:
    fila: pd.DataFrame
    eventos: pd.DataFrame
    procedimentos: pd.DataFrame
    hashes: dict = field(default_factory=dict)


def _hash(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fp:
        for bloco in iter(lambda: fp.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def carregar(dataset) -> Brutos:
    """Le os CSVs da pasta `dataset`. Toda coluna de texto permanece texto."""
    pasta = Path(dataset)
    brutos = {}
    hashes = {}
    for chave, nome in ARQUIVOS.items():
        caminho = pasta / nome
        if not caminho.exists():
            raise FileNotFoundError(f"arquivo ausente no dataset: {nome}")
        # dtype=str garante que CID nunca vire numero; datas convertidas depois.
        df = pd.read_csv(caminho, dtype=str, keep_default_na=True, na_values=[""])
        faltando = [c for c in COLUNAS_OBRIGATORIAS[chave] if c not in df.columns]
        if faltando:
            raise ValueError(f"coluna obrigatoria ausente em {nome}: {', '.join(faltando)}")
        for col in DATAS[chave]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        brutos[chave] = df
        hashes[nome] = _hash(caminho)
    return Brutos(fila=brutos["fila"], eventos=brutos["eventos"],
                  procedimentos=brutos["procedimentos"], hashes=hashes)
