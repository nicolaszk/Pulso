# -*- coding: utf-8 -*-
"""Passo 2 - Limpeza.

Normaliza campos, funde duplicatas, marca quem saiu da fila e separa os eventos
invalidos. Cada regra grava uma linha no relatorio (problema, quantidade, acao).
Nada se perde em silencio.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from . import config
from .texto import normalizar

_SO_ALNUM = re.compile(r"[^A-Za-z0-9]")


@dataclass
class Limpeza:
    solicitacoes: pd.DataFrame          # uma linha por solicitacao (mestre, duplicata ou saiu)
    eventos: pd.DataFrame               # eventos validos, remapeados ao mestre
    quarentena: list = field(default_factory=list)
    descartados_duplicados: int = 0
    relatorio: list = field(default_factory=list)

    def anotar(self, problema: str, quantidade: int, acao: str) -> None:
        self.relatorio.append({"problema": problema, "quantidade": int(quantidade), "acao": acao})


def _chave_sem_acento(s) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


def _cid_normal(s) -> str:
    return _SO_ALNUM.sub("", str(s or "").upper())


def _cid_exibicao(cid: str) -> str:
    return (cid[:3] + "." + cid[3:]) if len(cid) > 3 else cid


def _hash_conteudo(sol, data, tipo, resultado, valor, descricao) -> str:
    bruto = "|".join(str(x) for x in (sol, data, tipo, resultado, valor, descricao))
    return hashlib.sha256(bruto.encode()).hexdigest()


def _para_float(v):
    try:
        f = float(v)
        return f if pd.notna(f) else None
    except (TypeError, ValueError):
        return None


def limpar(fila: pd.DataFrame, eventos: pd.DataFrame, procs: pd.DataFrame,
           data_referencia: pd.Timestamp, saidas_por_evento: bool = True) -> Limpeza:
    """saidas_por_evento=False: so as observacoes tiram da fila aqui; os eventos de saida
    ficam para o processamento evento a evento (backend/src/pipeline), que pede aprovacao."""
    ref = pd.Timestamp(data_referencia)
    f = fila.copy()
    r = Limpeza(solicitacoes=f, eventos=eventos)

    # ------------------------------------------------------------------ normalizacao
    f["cid"] = f["cid_principal"].map(_cid_normal)
    f["cid_exibicao"] = f["cid"].map(_cid_exibicao)
    f["oncologico"] = f["cid"].str.startswith("C")
    r.anotar("cid normalizado (sem ponto, maiusculo)", (f["cid"] != f["cid_principal"].fillna("")).sum(),
             "comparado sem ponto, exibido com ponto")

    prio = f.get("prioridade_regulacao")
    f["prioridade_manual"] = prio.map(_chave_sem_acento) if prio is not None else ""
    vazias_prio = f["prioridade_manual"] == ""
    f.loc[vazias_prio, "prioridade_manual"] = "nao_informada"
    r.anotar("prioridade_regulacao vazia", vazias_prio.sum(), "marcada nao_informada (so informativa)")

    # municipio: agrupar por chave sem acento, usar a grafia mais frequente do grupo
    if "municipio" in f.columns:
        chave = f["municipio"].map(_chave_sem_acento)
        grafia = {}
        for k, grupo in f.groupby(chave)["municipio"]:
            modo = grupo.dropna().value_counts()
            grafia[k] = modo.index[0] if len(modo) else ""
        antes = f["municipio"].copy()
        f["municipio"] = chave.map(grafia)
        r.anotar("municipio com grafia inconsistente", (antes.fillna("") != f["municipio"].fillna("")).sum(),
                 "unificado pela grafia mais frequente")

    # distancia: vazia -> mediana do mesmo municipio; marcar imputada
    dist = pd.to_numeric(f.get("distancia_hospital_km"), errors="coerce")
    f["distancia_imputada"] = dist.isna()
    if "municipio" in f.columns:
        medianas = dist.groupby(f["municipio"]).transform("median")
        dist = dist.fillna(medianas)
    dist = dist.fillna(dist.median())
    f["distancia_hospital_km"] = dist
    r.anotar("distancia_hospital_km vazia", f["distancia_imputada"].sum(), "imputada pela mediana do municipio")

    # limitacao -> 0..3; vazia continua vazia
    lim = f.get("limitacao_funcional")
    f["limitacao"] = lim.map(lambda x: config.LIMITACAO.get(_chave_sem_acento(x))) if lim is not None else None

    # dor: inteiro 0..10; vazia continua vazia; fora da faixa -> vazia + relatorio
    dor = pd.to_numeric(f.get("intensidade_dor_eva"), errors="coerce")
    fora = dor.notna() & ((dor < 0) | (dor > 10))
    dor = dor.where(~fora)
    f["dor"] = dor
    r.anotar("intensidade_dor_eva fora de 0..10", fora.sum(), "esvaziada e registrada")

    # textos normalizados (originais preservados para exibicao)
    # campo vazio chega como NaN: sem o fillna vira o texto "nan"
    f["txt_justificativa"] = f.get("justificativa_clinica", pd.Series("", index=f.index)).fillna("").map(normalizar)
    f["txt_observacoes"] = f.get("observacoes", pd.Series("", index=f.index)).fillna("").map(normalizar)

    f["dias_em_fila"] = (ref - f["data_entrada_fila"]).dt.days

    # ------------------------------------------------------------------ duplicatas
    f["_ordem"] = f["solicitacao_id"].astype(str)
    f = f.sort_values(["data_entrada_fila", "_ordem"], na_position="last")
    grp = f.groupby(["paciente_id", "procedimento_id"], dropna=False)
    mestre_id = grp["solicitacao_id"].transform("first")
    f["mestre_id"] = mestre_id
    dup_mask = f["solicitacao_id"] != mestre_id

    # o mestre herda o pior valor de dor e de limitacao das copias
    for col in ("dor", "limitacao"):
        f[col] = grp[col].transform("max")
    # textos de todas as copias
    for col in ("txt_justificativa", "txt_observacoes", "justificativa_clinica", "observacoes"):
        if col in f.columns:
            f[col] = grp[col].transform(lambda s: " | ".join(dict.fromkeys(x for x in s if isinstance(x, str) and x)))

    remap = dict(zip(f.loc[dup_mask, "solicitacao_id"], f.loc[dup_mask, "mestre_id"]))
    f["status"] = "ativa"
    f.loc[dup_mask, "status"] = "duplicata"
    f["duplicata_fundida"] = f["solicitacao_id"].isin(set(remap.values()))
    r.anotar("solicitacoes duplicadas (mesmo paciente + procedimento)", dup_mask.sum(),
             "fundidas no mestre (entrada mais antiga)")

    # ------------------------------------------------------------------ eventos
    e = eventos.copy()
    e["solicitacao_id"] = e["solicitacao_id"].replace(remap)
    e["valor_numerico"] = e.get("valor_numerico").map(_para_float)
    e["hash_conteudo"] = [
        _hash_conteudo(s, d, t, res, val, desc)
        for s, d, t, res, val, desc in zip(
            e["solicitacao_id"], e["data_evento"], e["tipo_evento"],
            e["resultado"], e["valor_numerico"], e.get("descricao"))
    ]
    antes_dedup = len(e)
    e = e.drop_duplicates("hash_conteudo", keep="first")
    r.descartados_duplicados = antes_dedup - len(e)
    r.anotar("eventos repetidos (mesmo conteudo, id diferente)", r.descartados_duplicados, "descartados")

    ids_fila = set(f["solicitacao_id"])
    paciente_de = dict(zip(f["solicitacao_id"], f["paciente_id"]))
    validos = []
    for ev in e.to_dict("records"):
        motivo = _motivo_quarentena(ev, ids_fila, paciente_de, ref)
        if motivo:
            r.quarentena.append({"origem": "eventos_clinicos.csv", "motivo": motivo,
                                 "registro_json": json.dumps(_json_seguro(ev), ensure_ascii=False)})
        else:
            ev["data_recebimento"] = ref
            validos.append(ev)
    r.eventos = pd.DataFrame(validos)
    r.anotar("eventos em quarentena", len(r.quarentena), "guardados com o motivo")

    # ------------------------------------------------------------------ saida da fila
    _marcar_saidas(f, r.eventos if saidas_por_evento else r.eventos.iloc[0:0], r, ref)

    # ------------------------------------------------------------------ irma_com_evento
    f["irma_com_evento"] = _irmas_com_evento(f, r.eventos)

    r.solicitacoes = f.drop(columns=["_ordem"]).reset_index(drop=True)
    return r


def _motivo_quarentena(ev, ids_fila, paciente_de, ref) -> str | None:
    sol = ev["solicitacao_id"]
    if sol not in ids_fila:
        return "solicitacao_inexistente"
    data = ev["data_evento"]
    if pd.isna(data):
        return "data_invalida"
    if pd.Timestamp(data) > ref:
        return "data_futura"
    tipo = ev["tipo_evento"]
    if tipo not in config.TIPOS_EVENTO:
        return "tipo_desconhecido"
    if ev["resultado"] not in config.TIPOS_EVENTO[tipo]:
        return "resultado_desconhecido"
    if str(ev["paciente_id"]) != str(paciente_de.get(sol)):
        return "paciente_divergente"
    if tipo == "hba1c" and ev["valor_numerico"] is None:
        return "valor_ausente"
    return None


def _json_seguro(ev: dict) -> dict:
    saida = {}
    for k, v in ev.items():
        if isinstance(v, pd.Timestamp):
            saida[k] = None if pd.isna(v) else v.date().isoformat()
        elif pd.isna(v) if not isinstance(v, (list, dict)) else False:
            saida[k] = None
        else:
            saida[k] = v
    return saida


def _marcar_saidas(f: pd.DataFrame, eventos: pd.DataFrame, r: Limpeza, ref) -> None:
    f["evidencia_saida"] = None
    f["pendencias_saida"] = [[] for _ in range(len(f))]

    # 1. evento de saida (desistiu / cirurgia em outro servico), ate a data de referencia
    por_sol = {}
    if not eventos.empty:
        ev_saida = eventos[eventos["resultado"].isin(config.SAIDA_RESULTADOS_EVENTO)]
        for ev in ev_saida.to_dict("records"):
            if pd.notna(ev["data_evento"]) and pd.Timestamp(ev["data_evento"]) <= ref:
                por_sol.setdefault(ev["solicitacao_id"], ev)

    ativa = f["status"] == "ativa"
    saiu = 0
    for i in f.index[ativa]:
        sol = f.at[i, "solicitacao_id"]
        obs = f.at[i, "txt_observacoes"] or ""
        ev = por_sol.get(sol)
        if ev is not None:
            f.at[i, "status"] = "saiu"
            f.at[i, "evidencia_saida"] = (
                f"{ev['tipo_evento']}={ev['resultado']} em "
                f"{pd.Timestamp(ev['data_evento']).date()}: {ev.get('descricao') or ''}".strip())
            saiu += 1
        elif any(re.search(t, obs) for t in config.TERMOS_OBS_SAIU):
            f.at[i, "status"] = "saiu"
            f.at[i, "evidencia_saida"] = f"observacao: {obs}"
            saiu += 1
        else:
            if re.search(config.TERMO_OBS_SAIDA_PENDENTE, obs):
                f.at[i, "pendencias_saida"].append("confirmar_saida")
            if any(re.search(t, obs) for t in config.TERMOS_OBS_SEM_CONTATO):
                f.at[i, "pendencias_saida"].append("sem_contato")
    r.anotar("solicitacoes que sairam da fila", saiu, "status saiu, com a evidencia")


def _irmas_com_evento(f: pd.DataFrame, eventos: pd.DataFrame) -> pd.Series:
    """True se OUTRA solicitacao do mesmo paciente teve biopsia positiva ou internacao."""
    vazio = pd.Series(False, index=f.index)
    if eventos.empty:
        return vazio
    marcantes = eventos[((eventos["tipo_evento"] == "biopsia") & (eventos["resultado"] == "positivo"))
                        | (eventos["tipo_evento"] == "internacao")]
    sol_com = set(marcantes["solicitacao_id"])
    pac_de_sol = dict(zip(f["solicitacao_id"], f["paciente_id"]))
    pac_com = {pac_de_sol.get(s) for s in sol_com}
    resultado = []
    for sol, pac in zip(f["solicitacao_id"], f["paciente_id"]):
        tem_irma = pac in pac_com and not (sol in sol_com and
                   {s for s in sol_com if pac_de_sol.get(s) == pac} == {sol})
        resultado.append(bool(tem_irma))
    return pd.Series(resultado, index=f.index)
