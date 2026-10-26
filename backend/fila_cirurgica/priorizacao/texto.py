# -*- coding: utf-8 -*-
"""Normalizacao de texto e busca de termos com tratamento de negacao.

A busca e feita frase a frase: um termo so conta se aparece numa frase e nao
esta negado pelo trecho que vem antes dele, na mesma frase.
"""
from __future__ import annotations

import re
import unicodedata

from .config import NEGACAO_ANTES

# Negador no fim do trecho que precede o termo, com ate 3 palavras no meio.
# Ex.: "sem sinais de " -> negado;  "lesao com " -> nao negado.
_PALAVRAS = "|".join(
    (re.escape(n) if " " in n else r"\b" + re.escape(n) + (r"\w*" if n == "descartad" else r"\b"))
    for n in NEGACAO_ANTES
)
_NEG_RE = re.compile(r"(?:" + _PALAVRAS + r")(?:\s+\S+){0,3}\s*$")

_ESPACOS = re.compile(r"\s+")
_FRASES = re.compile(r"[.;!?\n]+")


def normalizar(texto) -> str:
    """Minusculo, sem acento, espacos colapsados. Preserva pontuacao de frase."""
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    s = s.lower()
    return _ESPACOS.sub(" ", s).strip()


def dividir_frases(texto_norm: str) -> list[str]:
    """Divide por . ; ! ? e quebras de linha. A negacao nunca atravessa a frase."""
    return [f.strip() for f in _FRASES.split(texto_norm) if f.strip()]


def _negado(trecho_antes: str) -> bool:
    return bool(_NEG_RE.search(trecho_antes.rstrip()))


def buscar_termo(texto_norm: str, termos: list[str]) -> str | None:
    """Devolve a frase onde o primeiro termo nao negado aparece, ou None.

    `termos` sao padroes regex aplicados sobre o texto ja normalizado.
    """
    if not texto_norm:
        return None
    for frase in dividir_frases(texto_norm):
        for padrao in termos:
            for m in re.finditer(padrao, frase):
                if not _negado(frase[: m.start()]):
                    return frase
    return None


def termo_negado(texto_norm: str, termo: str) -> bool:
    """True se o termo aparece mas TODAS as ocorrencias estao negadas.

    Util em testes de negacao. Se o termo nao aparece, devolve False.
    """
    achou = False
    for frase in dividir_frases(texto_norm):
        for m in re.finditer(termo, frase):
            achou = True
            if not _negado(frase[: m.start()]):
                return False
    return achou
