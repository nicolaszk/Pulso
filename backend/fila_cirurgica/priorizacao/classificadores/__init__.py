# -*- coding: utf-8 -*-
"""Registro fila -> classificador.

Trocar o classificador de uma fila e mudar uma linha aqui e subir a versao.
Nesta versao, todas as filas usam o classificador padrao; os especificos serao
avaliados depois e plugados sem mexer no resto.
"""
from __future__ import annotations

from .. import config
from .base import Classificador, ordenar_filas
from .prazo_padrao import PrazoPadrao

_PADRAO = PrazoPadrao()

REGISTRO: dict[str, Classificador] = {fila: _PADRAO for fila in config.PRAZO_FILA}

__all__ = ["REGISTRO", "ordenar_filas", "Classificador", "PrazoPadrao"]
