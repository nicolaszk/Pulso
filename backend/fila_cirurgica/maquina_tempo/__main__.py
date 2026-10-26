# -*- coding: utf-8 -*-
"""CLI da Maquina do Tempo.

  python -m maquina_tempo                      # manchete + top casos
  python -m maquina_tempo --json               # tudo em JSON
  python -m maquina_tempo --caso SOL-2026-00719  # linha do tempo de 1 paciente (demo)

Rodar de dentro de fila_cirurgica/. Dataset padrao: ../ideas/data/dataset.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from priorizacao import config

from . import metricas, replay
from .motor import processar_eventos, triagem_de_entrada

_RAIZ = Path(__file__).resolve().parents[2]
_DATASET_PADRAO = _RAIZ / "ideas" / "data" / "dataset"


def _fila(g: str) -> str:
    return f"{g} {config.NOME_FILA.get(g, g)}"


def _manchete(r: dict) -> None:
    p = r["promocoes"]
    d = p["dias_desde_promocao"]
    print(f"MAQUINA DO TEMPO · dataset na data {r['data_referencia']} · {r['ativas']} solicitacoes ativas")
    print("O motor reavaliou a fila a cada novo evento. Durante a espera, ele teria:")
    print(f"  * PROMOVIDO {p['n_promovidos']} pacientes de fila, reagindo a eventos clinicos;")
    print(f"  * destes, {p['prioridade_baixa_ou_media']} estavam em prioridade BAIXA ou MEDIA na regulacao manual;")
    print(f"  * {p['de_eletivo_ou_moderado']} entraram como eletivos/moderados (G6/G7) e subiram.")
    if d:
        print(f"  * ha quanto o sistema vinha sinalizando (1a promocao -> hoje): "
              f"mediana {d['mediana']} dias (media {d['media']}, p75 {d['p75']}, max {d['max']}).")
    print("\nMaiores saltos (fila de entrada -> fila apos os eventos):")
    for salto, n in list(p["saltos"].items())[:8]:
        print(f"  {n:3}x  {salto}")

    print("\nTop casos (maior salto de prioridade):")
    for c in p["casos"][:5]:
        print(f"  {c['solicitacao_id']}  {c['fila_entrada']} -> {c['fila_final']}  "
              f"(manual: {c['prioridade_manual']}; gatilho: {c['gatilho']}; "
              f"ha {c['dias_desde_promocao']} dias)")

    a = r["antecipacao"]
    if a["dias"]:
        print(f"\n(Secundario, honesto) Em {a['n_com_sinal']} dos {a['n_agudos']} pacientes que foram a "
              f"PS/internacao durante a espera havia um sinal clinico antes — "
              f"mediana {a['dias']['mediana']} dias de antecedencia.")
    c = r["consistencia"]
    print(f"\nConsistencia: {c['oncologico_prioridade_baixa']} oncologicos (C*) marcados como prioridade "
          f"BAIXA no manual; {c['biopsia_positiva_cid_nao_oncologico']} com biopsia positiva e CID ainda "
          f"nao oncologico; {c['prazo_estourado']} com prazo da fila estourado.")


def _caso(dataset: str, ref: str, sid: str) -> int:
    ativas, evs = replay.carregar_dataset(dataset, ref)
    row = next((a for a in ativas if a["solicitacao_id"] == sid), None)
    if row is None:
        print(f"solicitacao ativa nao encontrada: {sid}", file=sys.stderr)
        return 1
    eventos_sol = evs.get(sid, [])
    print(f"Paciente {sid} · CID {row.get('cid_exibicao')} · prioridade manual: {row.get('prioridade_manual')}")
    print(f"Entra na fila em: {_fila(triagem_de_entrada(row).fila)}")
    transicoes = processar_eventos(row, eventos_sol)
    if not transicoes:
        print("Nenhuma mudanca de fila ao longo dos eventos.")
    for t in transicoes:
        ev = t.evento_gatilho
        seta = "sobe" if t.sentido == "sobe" else "desce"
        print(f"  {t.data}  [{ev.get('tipo_evento')}/{ev.get('resultado')}]  "
              f"{t.fila_de} -> {t.fila_para}  ({seta})")
    subidas = [t for t in transicoes if t.sentido == "sobe"]
    if subidas:
        d1 = subidas[0].data
        p1 = replay.posicao_em(ativas, evs, d1, sid)
        ph = replay.posicao_em(ativas, evs, ref, sid)
        if p1 and ph:
            print(f"\nPosicao na fila de prioridades:")
            print(f"  em {d1} (1a promocao): {p1['posicao']}o de {p1['total']} ({_fila(p1['fila'])})")
            print(f"  hoje ({ref}):          {ph['posicao']}o de {ph['total']} ({_fila(ph['fila'])})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="maquina_tempo", description="Maquina do Tempo da fila cirurgica")
    ap.add_argument("--dataset", default=str(_DATASET_PADRAO))
    ap.add_argument("--data-referencia", default=config.DATA_REFERENCIA_PADRAO)
    ap.add_argument("--json", action="store_true", help="imprime o resumo completo em JSON")
    ap.add_argument("--caso", metavar="SOLICITACAO_ID", help="linha do tempo evento-a-evento de um paciente")
    a = ap.parse_args(argv)

    if a.caso:
        return _caso(a.dataset, a.data_referencia, a.caso)
    r = metricas.resumo(a.dataset, a.data_referencia)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        _manchete(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
