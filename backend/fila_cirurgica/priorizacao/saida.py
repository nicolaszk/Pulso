# -*- coding: utf-8 -*-
"""Passo 6 - Saida.

Monta a ordem final, confere a regra de ouro, gera os arquivos e devolve os itens
para o banco. Se a regra de ouro falhar, NADA e gravado e a execucao termina com
erro.
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import config


class RegraDeOuroViolada(Exception):
    pass


@dataclass
class Saida:
    itens: list              # linhas da fila ordenada (para o banco)
    tamanhos: dict           # fila -> n
    checagens: list          # (nome, ok, detalhe)
    arquivos: list


def _data_br(iso) -> str:
    if not iso:
        return ""
    a, m, d = str(iso)[:10].split("-")
    return f"{d}/{m}/{a}"


def _chave_ordem(r: dict):
    # fila -> data limite -> mais sinais -> mais dor (vazia por ultimo) -> entrada -> id
    return (r["ordem_fila"], r["data_limite_efetiva"], -r["n_sinais"],
            -(r["dor"] if r["dor"] is not None else -1),
            str(r["data_entrada_iso"]), str(r["solicitacao_id"]))


def _justificativa(r: dict) -> str:
    fila = f"{r['fila']} {config.NOME_FILA[r['fila']]} ({r['posicao_fila']}o da fila)"
    partes = [fila]
    motivo = r.get("motivo_texto")
    if motivo:
        partes.append(motivo)
    partes.append(f"entrada {_data_br(r['data_entrada_iso'])}, data limite {_data_br(r['data_limite_efetiva'])}")
    altas = [m["marcacao"] for m in r["marcacoes"] if m["severidade"] == "alta"]
    if altas:
        partes.append("ATENCAO: " + ", ".join(altas))
    return " | ".join(partes)


def gerar_saida(detalhe: list[dict], fora: list[dict], quarentena: list[dict],
                relatorio: list[dict], total_csv: int, saida_dir, data_referencia) -> Saida:
    # ------------------------------------------------------------------ ordem final
    ordenados = sorted(detalhe, key=_chave_ordem)
    # posicao na fila
    contagem_fila: Counter = Counter()
    for r in ordenados:
        contagem_fila[r["fila"]] += 1
        r["posicao_fila"] = contagem_fila[r["fila"]]
    for i, r in enumerate(ordenados, start=1):
        r["posicao"] = i
        r["justificativa"] = _justificativa(r)

    # ------------------------------------------------------------------ regra de ouro
    checagens = _checagens(ordenados, fora, total_csv)
    falhou = [c for c in checagens if not c[1]]
    if falhou:
        raise RegraDeOuroViolada("; ".join(f"{c[0]}: {c[2]}" for c in falhou))

    # ------------------------------------------------------------------ arquivos
    saida = Path(saida_dir)
    saida.mkdir(parents=True, exist_ok=True)
    arquivos = []

    arquivos.append(_csv(saida / "fila_priorizada.csv",
        ["solicitacao_id", "posicao", "justificativa"],
        [[r["solicitacao_id"], r["posicao"], r["justificativa"]] for r in ordenados]))

    arquivos.append(_csv(saida / "fila_detalhada.csv",
        ["posicao", "fila", "posicao_fila", "data_limite_efetiva", "prazo", "dias_em_fila",
         "solicitacao_id", "paciente_id", "cid", "sinais", "rotulos", "marcacoes", "pendencias",
         "proxima_revisao", "classificador", "classificador_versao", "prioridade_manual"],
        [[r["posicao"], r["fila"], r["posicao_fila"], r["data_limite_efetiva"], r["prazo"],
          r["dias_em_fila"], r["solicitacao_id"], r["paciente_id"], r["cid_exibicao"],
          ";".join(r["motivos"]), ";".join(r["rotulos"]),
          ";".join(m["marcacao"] for m in r["marcacoes"]), ";".join(r["pendencias"]),
          r["proxima_revisao"] or "", r["classificador"], r["classificador_versao"],
          r["prioridade_manual"]] for r in ordenados]))

    arquivos.append(_csv(saida / "fora_da_fila.csv",
        ["solicitacao_id", "status", "mestre_id", "evidencia"],
        [[x["solicitacao_id"], x["status"], x.get("mestre_id") or "", x.get("evidencia") or ""]
         for x in fora]))

    arquivos.append(_csv(saida / "quarentena.csv",
        ["origem", "motivo", "registro_json"],
        [[q["origem"], q["motivo"], q["registro_json"]] for q in quarentena]))

    sev = {"alta": 0, "media": 1, "baixa": 2, "informativa": 3}
    revisao = []
    for r in ordenados:
        for m in r["marcacoes"]:
            revisao.append([m["severidade"], r["solicitacao_id"], r["fila"], m["marcacao"]])
    revisao.sort(key=lambda x: (sev.get(x[0], 9), x[1]))
    arquivos.append(_csv(saida / "revisao_humana.csv",
        ["severidade", "solicitacao_id", "fila", "marcacao"], revisao))

    pend = []
    for r in ordenados:
        for p in r["pendencias"]:
            pend.append([r["solicitacao_id"], r["fila"], p])
    arquivos.append(_csv(saida / "pendencias.csv",
        ["solicitacao_id", "fila", "pendencia"], pend))

    tamanhos = {g[0]: contagem_fila.get(g[0], 0) for g in config.GRUPOS}
    arquivos.append(_relatorio(saida / "relatorio_carga.md", relatorio, tamanhos,
                               checagens, quarentena, fora, data_referencia))

    return Saida(itens=ordenados, tamanhos=tamanhos, checagens=checagens, arquivos=arquivos)


def _checagens(ordenados, fora, total_csv) -> list:
    checagens = []

    # 1. todo oncologico em G1a ou G2
    onco_fora = [r["solicitacao_id"] for r in ordenados if r["oncologico"] and r["fila"] not in ("G1a", "G2")]
    checagens.append(("oncologico_em_G1a_ou_G2", not onco_fora,
                      "ok" if not onco_fora else f"{len(onco_fora)} fora (ex.: {onco_fora[:3]})"))

    # 2. maior posicao de oncologico < menor posicao de sem urgencia clinica
    onco_pos = [r["posicao"] for r in ordenados if r["oncologico"]]
    calmos_pos = [r["posicao"] for r in ordenados if r["sem_urgencia"]]
    if onco_pos and calmos_pos:
        ok = max(onco_pos) < min(calmos_pos)
        detalhe = "ok" if ok else f"onco ate {max(onco_pos)} >= primeiro calmo {min(calmos_pos)}"
    else:
        ok, detalhe = True, "sem oncologicos ou sem pacientes calmos"
    checagens.append(("regra_de_ouro", ok, detalhe))

    # 3. posicoes unicas e contiguas
    posicoes = sorted(r["posicao"] for r in ordenados)
    contiguo = posicoes == list(range(1, len(ordenados) + 1))
    checagens.append(("posicoes_unicas_contiguas", contiguo,
                      "ok" if contiguo else "posicoes nao contiguas"))

    # 4. toda solicitacao do CSV tem destino
    destinos = len(ordenados) + len(fora)
    checagens.append(("cobertura_total", destinos == total_csv,
                      f"{destinos}/{total_csv}"))
    return checagens


def _csv(caminho: Path, header, linhas) -> Path:
    with open(caminho, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(header)
        w.writerows(linhas)
    return caminho


def _relatorio(caminho, relatorio, tamanhos, checagens, quarentena, fora, data_referencia) -> Path:
    linhas = [f"# Relatorio de carga - {data_referencia}", "",
              f"Versao das regras: {config.REGRAS_VERSAO}", "",
              "## Limpeza (passo 2)", "", "| Problema | Qtde | Acao |", "|---|---|---|"]
    for r in relatorio:
        linhas.append(f"| {r['problema']} | {r['quantidade']} | {r['acao']} |")

    qmot = Counter(q["motivo"] for q in quarentena)
    linhas += ["", "## Quarentena de eventos", ""]
    for mot, n in sorted(qmot.items()):
        linhas.append(f"- {mot}: {n}")

    fstat = Counter(x["status"] for x in fora)
    linhas += ["", "## Fora da fila", ""]
    for st, n in sorted(fstat.items()):
        linhas.append(f"- {st}: {n}")

    linhas += ["", "## Tamanho de cada fila", "", "| Fila | Nome | n |", "|---|---|---|"]
    for g, nome, _ in config.GRUPOS:
        linhas.append(f"| {g} | {nome} | {tamanhos.get(g, 0)} |")

    linhas += ["", "## Checagens", ""]
    for nome, ok, det in checagens:
        linhas.append(f"- [{'x' if ok else ' '}] {nome}: {det}")
    linhas.append("")
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho
