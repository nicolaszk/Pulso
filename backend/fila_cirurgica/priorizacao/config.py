# -*- coding: utf-8 -*-
"""Constantes e versao das regras.

Mudar QUALQUER valor aqui exige subir REGRAS_VERSAO: mesma entrada + mesma data
+ mesma versao de regras = mesma saida, byte a byte.
"""
from __future__ import annotations

REGRAS_VERSAO = "2.0.0"

# "Hoje" padrao do calculo. Nunca fixado no codigo de calculo: sempre vem por parametro.
DATA_REFERENCIA_PADRAO = "2026-10-23"

# Janelas e fatores (dias / fracoes)
JANELA_PIORA_DIAS = 180
TEXTO_ANTIGO_DIAS = 365
ALERTA_PRAZO_FRACAO = 0.8
FATOR_PRAZO_ESTOURADO = 2.0
FATOR_MIN_PRAZO = 0.25  # limite inferior dos classificadores
HBA1C_DESCONTROLE = 8.5
CONFIANCA_MINIMA = 0.5
JUSTIFICATIVA_POBRE_MIN = 40

# Mapeamento de limitacao funcional para 0..3
LIMITACAO = {"nenhuma": 0, "leve": 1, "moderada": 2, "grave": 3}

# CIDs (comparados sem ponto, maiusculos)
CID_URGENTES = {"I200", "K400", "K403", "K420", "K430", "K800", "N132", "I832"}
REGEX_CID_INCERTO = r"^(D3[7-9]|D4[0-8]|D05|R91)"

# Filas, em ordem fixa, com o prazo de referencia (dias). A ordem entre filas e inegociavel.
GRUPOS = [
    ("G1a", "Oncologico em progressao", 15),
    ("G1b", "Agudo nao oncologico", 15),
    ("G2", "Oncologico confirmado", 21),
    ("G3", "Suspeita oncologica", 60),
    ("G4", "Deterioracao recente", 60),
    ("G5", "Alta carga de sintomas", 60),
    ("G6", "Sintomatico moderado", 180),
    ("G7", "Eletivo estavel", 360),
]
ORDEM_FILA = {g[0]: i for i, g in enumerate(GRUPOS)}
NOME_FILA = {g[0]: g[1] for g in GRUPOS}
PRAZO_FILA = {g[0]: g[2] for g in GRUPOS}

# Dominio dos eventos: tipo -> resultados validos. Fora disso vai para a quarentena.
TIPOS_EVENTO = {
    "biopsia": {"positivo", "negativo", "inconclusivo"},
    "hba1c": {"resultado"},
    "pronto_socorro": {"atendido_liberado", "observacao"},
    "internacao": {"alta"},
    "exame_imagem": {"estavel", "progressao"},
    "consulta_reavaliacao": {"piora", "estavel", "melhora"},
    "contato_telefonico": {
        "atendeu", "nao_atendeu", "relata_piora", "relata_melhora",
        "informou_cirurgia_outro_servico", "desistiu",
    },
    "falta": {"consulta", "exame", "avaliacao_pre_anestesica"},
}

# Negacao no texto: um termo e negado se o trecho antes dele, na mesma frase,
# termina num destes negadores com ate 3 palavras no meio.
NEGACAO_ANTES = ["sem", "nega", "negou", "ausencia de", "nao ha", "descartad"]

# Termos de texto (padroes regex, aplicados sobre texto ja normalizado).
# texto_agudo -> G1b (agudo nao oncologico)
TERMOS_AGUDO = [
    r"encarcer", r"estrangul", r"suboclus", r"obstrucao intestinal",
    r"retencao urinaria aguda", r"hidronefrose", r"colangite", r"\bsepse\b",
    r"pancreatite", r"abdome agudo", r"enterorragia", r"melena", r"hematemese",
    r"hemoptise", r"angina (?:em repouso|instavel)", r"sincope", r"dessaturacao",
    r"retencao de co2", r"isquemia (?:aguda|critica)",
]
# texto_alarme -> G1a (oncologico em progressao) e G4 (deterioracao)
TERMOS_ALARME = [
    r"sangramento espontaneo", r"transfund", r"crescimento rapido",
    r"linfonodo.*(?:fixo|palpavel)", r"perda ponderal", r"emagrecimento",
    r"disfagia", r"rouquidao", r"psa em elevacao", r"massa anexial", r"ca-?125",
    r"perda de funcao", r"dano neurologico", r"acamad", r"ulcera de pressao",
    r"quedas de repeticao", r"glaucoma facomorfico", r"icter",
]
# texto_suspeita -> G3 (suspeita oncologica)
TERMOS_SUSPEITA = [
    r"carcinoma", r"malign", r"suspeit", r"atipia", r"neoplasia",
    r"bi-?rads ?[45]", r"pi-?rads ?[45]", r"bethesda (?:iv|v|vi)\b",
    r"lesao suspeita", r"nodulo suspeito",
]
# obs_piora -> observacoes (sem data: somente_texto, nao expira)
TERMOS_OBS_PIORA = [r"piora", r"agrav", r"agilizar"]

# Saida da fila
SAIDA_RESULTADOS_EVENTO = {"desistiu", "informou_cirurgia_outro_servico"}
TERMOS_OBS_SAIU = [
    r"desistiu", r"retirada da fila", r"outro servico", r"operou pelo convenio",
    r"cirurgia em outro servico",
]
TERMO_OBS_SAIDA_PENDENTE = r"nao deseja mais operar no momento"
TERMOS_OBS_SEM_CONTATO = [r"mudou de endereco", r"numero nao existe", r"sem sucesso"]


def config_json() -> dict:
    """Snapshot das regras para gravar junto de cada versao da fila."""
    return {
        "REGRAS_VERSAO": REGRAS_VERSAO,
        "JANELA_PIORA_DIAS": JANELA_PIORA_DIAS,
        "TEXTO_ANTIGO_DIAS": TEXTO_ANTIGO_DIAS,
        "ALERTA_PRAZO_FRACAO": ALERTA_PRAZO_FRACAO,
        "FATOR_PRAZO_ESTOURADO": FATOR_PRAZO_ESTOURADO,
        "FATOR_MIN_PRAZO": FATOR_MIN_PRAZO,
        "HBA1C_DESCONTROLE": HBA1C_DESCONTROLE,
        "CONFIANCA_MINIMA": CONFIANCA_MINIMA,
        "CID_URGENTES": sorted(CID_URGENTES),
        "REGEX_CID_INCERTO": REGEX_CID_INCERTO,
        "GRUPOS": [{"fila": g, "nome": n, "prazo": p} for g, n, p in GRUPOS],
    }
