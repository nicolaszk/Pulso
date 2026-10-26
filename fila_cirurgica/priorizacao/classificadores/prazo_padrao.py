# -*- coding: utf-8 -*-
"""Classificador padrao.

data_limite_efetiva = data_entrada_fila + prazo da fila; confianca = 1.
Dentro de uma fila, ordenar por essa data equivale a ordenar pela entrada mais
antiga, e a ordem nao muda com o passar do tempo.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from .. import config


class PrazoPadrao:
    nome = "prazo_padrao"
    versao = "1.0.0"
    filas = set(config.PRAZO_FILA)

    def avaliar(self, pacientes: pd.DataFrame, data_referencia) -> pd.DataFrame:
        linhas = []
        for row in pacientes.to_dict("records"):
            prazo = config.PRAZO_FILA[row["fila"]]
            entrada = pd.Timestamp(row["data_entrada_fila"])
            limite = entrada + timedelta(days=prazo)
            linhas.append({
                "solicitacao_id": row["solicitacao_id"],
                "data_limite_efetiva": limite.date().isoformat(),
                "componentes": [],
                "confianca": 1.0,
                "evidencias": [],
            })
        return pd.DataFrame(linhas)
