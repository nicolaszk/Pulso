# -*- coding: utf-8 -*-
"""Maquina do Tempo: modulo adjacente as filas.

Rebobina o log de eventos e mede o beneficio do motor frente a revisao manual
periodica. O coracao e um motor de reavaliacao incremental (motor.py): a cada
novo evento o paciente e reavaliado com todos os eventos ate aquela data, exatamente
como o `reavaliar` de producao, mas standalone (so depende de `priorizacao`, le os CSVs,
nao toca na fila oficial nem precisa de banco).
"""
from __future__ import annotations

from .motor import Reavaliacao, Transicao, processar_eventos, reavaliar

__all__ = ["Reavaliacao", "Transicao", "reavaliar", "processar_eventos"]
