# -*- coding: utf-8 -*-
"""Passo 5 - Contrato dos classificadores + orquestrador.

Cada classificador devolve a DATA LIMITE EFETIVA de cada paciente, nunca uma
posicao. O orquestrador aplica as regras que valem para qualquer classificador:
mesmo conjunto de ids, limites de data, plano B por paciente e registro.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Protocol

import pandas as pd

from .. import config


class Classificador(Protocol):
    nome: str
    versao: str
    filas: set

    def avaliar(self, pacientes: pd.DataFrame, data_referencia) -> pd.DataFrame:
        """Recebe so os pacientes da sua fila; devolve uma linha por paciente com
        solicitacao_id, data_limite_efetiva, componentes, confianca, evidencias."""
        ...


def ordenar_filas(triados: pd.DataFrame, registro: dict, data_referencia) -> pd.DataFrame:
    """Devolve a data limite efetiva por paciente, fila a fila.

    `triados` tem, por linha: solicitacao_id, fila, data_entrada_fila.
    `registro` mapeia fila -> classificador.
    """
    from .prazo_padrao import PrazoPadrao
    padrao = PrazoPadrao()
    linhas = []
    falhas = []
    for fila, grupo in triados.groupby("fila"):
        clf = registro.get(fila, padrao)
        resultado = _avaliar_fila(clf, padrao, grupo, fila, data_referencia, falhas)
        linhas.append(resultado)
    out = pd.concat(linhas, ignore_index=True) if linhas else pd.DataFrame()
    out.attrs["falhas"] = falhas
    return out


def _avaliar_fila(clf, padrao, grupo, fila, data_referencia, falhas) -> pd.DataFrame:
    ids = list(grupo["solicitacao_id"])
    try:
        resp = clf.avaliar(grupo.copy(), data_referencia)
        mesmo = set(resp["solicitacao_id"]) == set(ids) and len(resp) == len(ids)
        if not mesmo:
            raise ValueError("conjunto de ids diferente do recebido")
        usado = clf
    except Exception as exc:  # fila inteira cai para o padrao
        falhas.append({"fila": fila, "classificador": getattr(clf, "nome", "?"), "erro": str(exc)})
        resp = padrao.avaliar(grupo.copy(), data_referencia)
        usado = padrao

    resp = resp.merge(grupo[["solicitacao_id", "data_entrada_fila"]], on="solicitacao_id", how="left")
    prazo = config.PRAZO_FILA[fila]
    linhas = []
    for row in resp.to_dict("records"):
        entrada = pd.Timestamp(row["data_entrada_fila"])
        minimo = entrada + timedelta(days=int(config.FATOR_MIN_PRAZO * prazo))
        maximo = entrada + timedelta(days=prazo)
        data = row.get("data_limite_efetiva")
        confianca = row.get("confianca", 1.0)
        marcacoes = []
        # Plano B por paciente: data vazia ou confianca baixa -> padrao + marcacao
        if data is None or pd.isna(pd.Timestamp(data)) or (confianca is not None and confianca < config.CONFIANCA_MINIMA):
            data = maximo
            marcacoes.append("revisao_classificador")
        data = pd.Timestamp(data)
        # Limites: nunca antes de entrada+0.25*prazo nem depois do prazo da fila
        data = min(max(data, minimo), maximo)
        linhas.append({
            "solicitacao_id": row["solicitacao_id"],
            "data_limite_efetiva": data.date().isoformat(),
            "classificador": usado.nome,
            "classificador_versao": usado.versao,
            "componentes": row.get("componentes") or [],
            "confianca": float(confianca) if confianca is not None else 1.0,
            "marcacoes_classificador": marcacoes,
        })
    return pd.DataFrame(linhas)
