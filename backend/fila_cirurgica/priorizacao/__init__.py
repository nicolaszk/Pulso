# -*- coding: utf-8 -*-
"""Priorizacao da fila cirurgica (passos 1 a 6).

Funcoes publicas:
  carregar(dataset)                               -> brutos + hashes
  limpar(fila, eventos, procs, data_ref)          -> fila tratada, eventos, quarentena, relatorio
  montar_estado(solicitacao, eventos, data_ref)   -> Estado (sinais + evidencias)
  triar(estado, data_ref)                         -> fila, motivos, rotulos, marcacoes, pendencias
  ordenar_filas(triados, registro, data_ref)      -> data limite efetiva por paciente
  gerar_saida(...)                                -> arquivos + itens para o banco
  carga_inicial(...)                              -> encadeia tudo e devolve o resumo
"""
from __future__ import annotations

from .carga import carregar
from .classificadores import REGISTRO, ordenar_filas
from .config import REGRAS_VERSAO
from .limpeza import limpar
from .pipeline import carga_inicial
from .saida import gerar_saida
from .sinais import Estado, montar_estado
from .triagem import Triagem, triar

__all__ = [
    "carregar", "limpar", "montar_estado", "triar", "ordenar_filas", "gerar_saida",
    "carga_inicial", "Estado", "Triagem", "REGISTRO", "REGRAS_VERSAO",
]
