# -*- coding: utf-8 -*-
"""CLI.

  python -m priorizacao carga --dataset dataset/ --data-referencia 2026-10-23 \
    --banco saida/fila.sqlite --saida saida/ [--recriar]

Codigo de saida 0 so se todas as checagens passaram.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .pipeline import carga_inicial
from .saida import RegraDeOuroViolada

# dataset do repositorio, por padrao (ideas/data/dataset)
_RAIZ = Path(__file__).resolve().parents[2]
_DATASET_PADRAO = _RAIZ / "ideas" / "data" / "dataset"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="priorizacao")
    sub = ap.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("carga", help="carga inicial (passos 1 a 6)")
    c.add_argument("--dataset", default=str(_DATASET_PADRAO))
    c.add_argument("--data-referencia", default=config.DATA_REFERENCIA_PADRAO)
    c.add_argument("--banco", default="saida/fila.sqlite")
    c.add_argument("--saida", default="saida")
    c.add_argument("--recriar", action="store_true")
    a = ap.parse_args(argv)

    if a.comando == "carga":
        try:
            r = carga_inicial(a.dataset, a.data_referencia, a.banco, a.saida, a.recriar)
        except RegraDeOuroViolada as exc:
            print(f"REGRA DE OURO VIOLADA: {exc}\nNada foi gravado.", file=sys.stderr)
            return 2
        _relatar(r)
        return 0 if all(ok for _, ok, _ in r.checagens) else 1
    return 1


def _relatar(r) -> None:
    print(f"Data de referencia: {r.data_referencia}  |  regras {config.REGRAS_VERSAO}")
    print(f"{r.total_csv} solicitacoes | {r.ativas} ativas | {r.duplicatas} duplicatas | {r.saidas} saidas")
    print(f"quarentena: {r.quarentena} eventos | duplicados descartados: {r.duplicados_descartados}")
    print("Tamanho das filas:")
    for g, nome, _ in config.GRUPOS:
        print(f"  {g:4} {nome:28} {r.tamanhos.get(g, 0)}")
    if r.falhas_classificador:
        print("Falhas de classificador (fila caiu para o padrao):")
        for f in r.falhas_classificador:
            print(f"  {f['fila']}: {f['erro']}")
    print("Checagens:")
    for nome, ok, det in r.checagens:
        print(f"  [{'x' if ok else ' '}] {nome}: {det}")
    print(f"Versao da fila gravada: {r.versao_id}")
    print("Arquivos:")
    for a in r.arquivos:
        print(f"  {a}")


if __name__ == "__main__":
    sys.exit(main())
