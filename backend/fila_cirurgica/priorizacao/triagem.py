# -*- coding: utf-8 -*-
"""Passo 4 - Triagem.

triar(estado, data_referencia) decide a fila de UMA solicitacao ativa. A ordem
entre as filas e fixa; nenhum passo seguinte pode altera-la. A triagem e o unico
passo que decide a fila.

Invariante: maligno => fila em {G1a, G2}. Se falhar, levanta erro.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import config
from .sinais import Estado


@dataclass
class Triagem:
    solicitacao_id: str
    fila: str
    motivos: list = field(default_factory=list)       # sinais que decidiram a fila
    rotulos: list = field(default_factory=list)        # todos os sinais ativos
    marcacoes: list = field(default_factory=list)      # {marcacao, severidade}
    pendencias: list = field(default_factory=list)     # operacionais
    proxima_revisao: str | None = None


_SEVERIDADE = {"alta": 0, "media": 1, "baixa": 2, "informativa": 3}


def triar(estado: Estado, data_referencia, pendencias_saida: list | None = None) -> Triagem:
    e = estado
    ref = _dia(data_referencia)

    confirmar_saida_g4 = False
    if e.maligno:
        # Invariante: oncologico/maligno so vive em G1a ou G2.
        if (e.progressao_imagem or e.reavaliacao_piora or e.pronto_socorro
                or e.internacao or e.texto_alarme):
            fila, motivos = "G1a", _presentes(e, [
                "progressao_imagem", "reavaliacao_piora", "pronto_socorro", "internacao", "texto_alarme"])
        else:
            fila, motivos = "G2", ["maligno"]
    elif e.cid_urgente or e.texto_agudo:
        fila, motivos = "G1b", _presentes(e, ["cid_urgente", "texto_agudo"])
    elif e.cid_incerto or e.texto_suspeita:
        fila, motivos = "G3", _presentes(e, ["cid_incerto", "texto_suspeita"])
    elif e.piora_recente or e.obs_piora or e.texto_alarme:
        fila, motivos = "G4", _presentes(e, [
            "progressao_imagem", "reavaliacao_piora", "pronto_socorro",
            "internacao", "relata_piora", "obs_piora", "texto_alarme"])
    elif e.piora_qualquer:
        # unica razao para G4 e piora expirada (>180 d): mantem G4, confirma com o regulador
        fila, motivos, confirmar_saida_g4 = "G4", ["piora_expirada"], True
    elif (e.dor is not None and e.dor >= 7) or e.limitacao == 3:
        fila, motivos = "G5", _sintoma_alto(e)
    elif (e.dor is not None and 4 <= e.dor <= 6) or e.limitacao == 2:
        fila, motivos = "G6", _sintoma_moderado(e)
    else:
        fila, motivos = "G7", ["eletivo_estavel"]

    if e.maligno and fila not in ("G1a", "G2"):
        raise AssertionError(f"invariante violada: {e.solicitacao_id} maligno em {fila}")

    t = Triagem(solicitacao_id=e.solicitacao_id, fila=fila, motivos=motivos,
                rotulos=sorted(e.sinais_validos))
    _marcacoes(e, t, fila, confirmar_saida_g4)
    _pendencias(e, t, pendencias_saida or [])
    t.proxima_revisao = _proxima_revisao(e, fila, ref)
    t.marcacoes.sort(key=lambda m: _SEVERIDADE.get(m["severidade"], 9))
    return t


def _presentes(e: Estado, nomes: list[str]) -> list[str]:
    return [n for n in nomes if getattr(e, n, False)]


def _sintoma_alto(e: Estado) -> list[str]:
    m = []
    if e.dor is not None and e.dor >= 7:
        m.append("dor_alta")
    if e.limitacao == 3:
        m.append("limitacao_grave")
    return m


def _sintoma_moderado(e: Estado) -> list[str]:
    m = []
    if e.dor is not None and 4 <= e.dor <= 6:
        m.append("dor_moderada")
    if e.limitacao == 2:
        m.append("limitacao_moderada")
    return m


def _texto_only(e: Estado, fila: str) -> bool:
    """A fila e sustentada SO por texto?"""
    if fila == "G1a":
        return e.texto_alarme and not (e.progressao_imagem or e.reavaliacao_piora
                                       or e.pronto_socorro or e.internacao)
    if fila == "G1b":
        return e.texto_agudo and not e.cid_urgente
    if fila == "G3":
        return e.texto_suspeita and not e.cid_incerto
    return False


def _marcacoes(e: Estado, t: Triagem, fila: str, confirmar_saida_g4: bool) -> None:
    def add(nome, sev):
        t.marcacoes.append({"marcacao": nome, "severidade": sev})

    if e.biopsia_positiva and not e.oncologico:
        add("atualizar_cid", "alta")
    if e.conflito_laudos:
        add("conflito_laudos", "alta")
    if _texto_only(e, fila):
        add("somente_texto", "alta")
        if e.dias_em_fila > config.TEXTO_ANTIGO_DIAS:
            add("texto_antigo", "media")
    if confirmar_saida_g4:
        add("confirmar_saida_g4", "media")
    if fila in ("G1a", "G1b", "G2", "G3", "G4") and e.justificativa_tamanho < config.JUSTIFICATIVA_POBRE_MIN:
        add("justificativa_pobre", "media")
    if e.dados_faltantes:
        add("dados_faltantes", "media")
    if (e.flag_oncologico != e.maligno) or (e.flag_piora != (e.piora_recente or e.obs_piora)) \
            or (e.flag_diabetico != e.diabetico_dado):
        add("flag_divergente", "baixa")

    prazo = config.PRAZO_FILA[fila]
    if e.dias_em_fila > config.FATOR_PRAZO_ESTOURADO * prazo:
        add("prazo_estourado", "informativa")
    elif e.dias_em_fila >= config.ALERTA_PRAZO_FRACAO * prazo:
        add("alerta_prazo", "informativa")


def _pendencias(e: Estado, t: Triagem, pendencias_saida: list) -> None:
    p = list(dict.fromkeys(pendencias_saida))  # sem_contato / confirmar_saida das observacoes
    if e.nao_atendeu >= 2:
        p.append("nao_atendeu_2x")
    if e.faltas >= 2:
        p.append("faltas_2x")
    if e.hba1c_atual is not None and e.hba1c_atual > config.HBA1C_DESCONTROLE:
        p.append("hba1c_alta")
    if e.duplicata_fundida:
        p.append("duplicata_fundida")
    if e.irma_com_evento:
        p.append("irma_com_evento")
    t.pendencias = list(dict.fromkeys(p))


def _proxima_revisao(e: Estado, fila: str, ref: date | None) -> str | None:
    if ref is None or e.data_entrada is None:
        return None
    prazo = config.PRAZO_FILA[fila]
    candidatos = [
        e.data_entrada + timedelta(days=int(config.ALERTA_PRAZO_FRACAO * prazo)),
        e.data_entrada + timedelta(days=prazo),
        e.data_entrada + timedelta(days=int(config.FATOR_PRAZO_ESTOURADO * prazo)),
    ]
    if fila in ("G1a", "G4") and e.ultima_piora is not None:
        candidatos.append(e.ultima_piora + timedelta(days=config.JANELA_PIORA_DIAS))
    if _texto_only(e, fila):
        candidatos.append(e.data_entrada + timedelta(days=config.TEXTO_ANTIGO_DIAS))
    futuros = sorted(d for d in candidatos if d > ref)
    return futuros[0].isoformat() if futuros else None


def _dia(v) -> date | None:
    from .sinais import _dia as d
    return d(v)
