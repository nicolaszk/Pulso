"""CLI do pipeline (rodar de backend/).

  python -m src.pipeline rodar --recriar          passos 1-5: CSVs -> limpeza -> eventos -> banco -> processamento
  python -m src.pipeline carregar --recriar       so 1-4 (eventos ficam pendentes)
  python -m src.pipeline carregar --recriar --ate-pedidos 3
                                                  1-4 e processa eventos ate haver 3 pedidos para o medico (demo)
  python -m src.pipeline processar [--limite N | --ate-pedidos N]   tira eventos da fila de processamento
  python -m src.pipeline mudancas [--status pendente]
  python -m src.pipeline decidir ID aprovar|rejeitar --medico 1 [--motivo "..."]
  python -m src.pipeline aprovar-todas --medico 1 (demo/teste: fila oficial = recomendada)
  python -m src.pipeline varrer [--data AAAA-MM-DD]
  python -m src.pipeline explicar mudancas|fila [--limite N|0=todos] [--paralelo 4]   texto claro pelo LLM
  python -m src.pipeline salvar-explicacoes     grava os textos do LLM em db/explicacoes.jsonl (a carga importa)
  python -m src.pipeline exportar [--modo recomendada|oficial] [--saida saida/fila_priorizada.csv] [--explicacao]
  python -m src.pipeline resumo
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from .. import db
from . import carga, consultas, explicacao, fila, processamento


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("rodar", "carregar"):
        p = sub.add_parser(nome)
        p.add_argument("--recriar", action="store_true", help="apaga o banco e carrega de novo")
        p.add_argument("--se-vazio", action="store_true", help="carrega so se o banco ainda estiver vazio (docker compose up)")
        p.add_argument("--dataset")
        p.add_argument("--data-referencia")
    sub.choices["carregar"].add_argument(
        "--ate-pedidos", type=int, metavar="N",
        help="depois da carga, processa eventos ate a caixa do medico ter N pedidos pendentes")
    p = sub.add_parser("processar")
    p.add_argument("--limite", type=int)
    p.add_argument("--ate-pedidos", type=int, metavar="N", help="processa ate haver N pedidos pendentes")
    p = sub.add_parser("mudancas")
    p.add_argument("--status", default="pendente")
    p.add_argument("--limite", type=int, default=20)
    p = sub.add_parser("decidir")
    p.add_argument("id", type=int)
    p.add_argument("decisao", choices=["aprovar", "rejeitar"])
    p.add_argument("--medico", type=int, required=True)
    p.add_argument("--motivo")
    p = sub.add_parser("aprovar-todas")
    p.add_argument("--medico", type=int, required=True)
    p = sub.add_parser("varrer")
    p.add_argument("--data")
    p = sub.add_parser("explicar", help="gera o texto claro dos pedidos pendentes ou do topo da fila")
    p.add_argument("alvo", choices=["mudancas", "fila"])
    p.add_argument("--limite", type=int, default=10, help="0 = todos")
    p.add_argument("--paralelo", type=int, default=4, help="chamadas ao LLM ao mesmo tempo")
    sub.add_parser("salvar-explicacoes", help="grava os textos aceitos em db/explicacoes.jsonl")
    p = sub.add_parser("exportar")
    p.add_argument("--modo", default="recomendada", choices=["recomendada", "oficial"])
    p.add_argument("--saida", default="saida/fila_priorizada.csv")
    p.add_argument("--explicacao", action="store_true", help="justificativa = texto do LLM ja gerado, onde houver")
    sub.add_parser("resumo")
    a = ap.parse_args(argv)

    with db.conectar() as con:
        t0 = time.time()
        if a.cmd in ("rodar", "carregar"):
            from pathlib import Path
            if a.se_vazio and db.banco_populado(con):
                print("banco ja carregado; nada a fazer")
                return 0
            r = carga.carregar(con, Path(a.dataset) if a.dataset else None, a.data_referencia, a.recriar)
            _imprimir("carga (passos 1-4)", r)
            if a.cmd == "rodar":
                _imprimir("processamento (passo 5)", processamento.processar_pendentes(con))
                _imprimir_resumo(consultas.resumo(con))
            elif a.ate_pedidos:
                _imprimir("processamento (ate pedidos)", processamento.processar_ate_pedidos(con, a.ate_pedidos))
        elif a.cmd == "processar":
            if a.ate_pedidos:
                _imprimir("processamento", processamento.processar_ate_pedidos(con, a.ate_pedidos))
            else:
                _imprimir("processamento", processamento.processar_pendentes(con, a.limite))
        elif a.cmd == "mudancas":
            for m in consultas.mudancas(con, None if a.status == "todas" else a.status, a.limite):
                print(f"#{m['id']:<5} {m['status']:<10} {m['tipo']:<6} {m['solicitacao_id']}  "
                      f"{m['fila_atual']}@{m['posicao_atual']} -> {m['fila_proposta'] or 'fora'}@{m['posicao_proposta'] or '-'}"
                      f"  {m['motivo'][:110]}")
        elif a.cmd == "decidir":
            _imprimir("decisao", fila.decidir(con, a.id, a.decisao == "aprovar", a.medico, a.motivo))
        elif a.cmd == "aprovar-todas":
            n = 0
            while pend := consultas.mudancas(con, "pendente", limite=1):
                fila.decidir(con, pend[0]["id"], True, a.medico, "aprovacao em lote (demo)")
                n += 1
            print(f"{n} pedidos aprovados")
        elif a.cmd == "varrer":
            _imprimir("varredura", processamento.varrer(con, a.data))
        elif a.cmd == "explicar":
            _explicar(con, a.alvo, a.limite, a.paralelo)
        elif a.cmd == "salvar-explicacoes":
            _salvar_explicacoes(con)
        elif a.cmd == "exportar":
            print(consultas.exportar(con, a.saida, a.modo, a.explicacao))
        elif a.cmd == "resumo":
            _imprimir_resumo(consultas.resumo(con))
        print(f"({time.time() - t0:.1f} s)", file=sys.stderr)
    return 0


def _explicar(con, alvo: str, limite: int, paralelo: int) -> None:
    """Gera em paralelo (uma conexao por chamada); com Ollama, rode com OLLAMA_NUM_PARALLEL >= paralelo."""
    from concurrent.futures import ThreadPoolExecutor

    from ..llm import LLM, LLMIndisponivel
    try:
        llm = LLM()
    except LLMIndisponivel as exc:
        print(f"LLM indisponivel: {exc}", file=sys.stderr)
        return
    n = limite or 100_000
    if alvo == "mudancas":
        ids = [("mudanca", m["id"]) for m in consultas.mudancas(con, "pendente", n)]
    else:
        ids = [("solicitacao", r["solicitacao_id"]) for r in consultas.fila(con, "recomendada", limite=n)]
    print(f"{llm.provedor}/{llm.modelo}: {len(ids)} textos, {paralelo} por vez")
    detalhar = len(ids) <= 20

    def um(item):
        with db.conectar() as c:
            return item, explicacao.explicar(c, item[0], item[1], LLM(llm.provedor, llm.modelo))

    contagem, t0 = {}, time.time()
    with ThreadPoolExecutor(max(1, paralelo)) as pool:
        for k, ((tipo, i), r) in enumerate(pool.map(um, ids), 1):
            chave = "cache" if r.get("em_cache") else r["fonte"]
            contagem[chave] = contagem.get(chave, 0) + 1
            if detalhar:
                print(f"\n[{chave}] {tipo} {i}" + (f"  ({r['motivo']})" if r.get("motivo") else ""))
                print(f"  {r['texto']}")
            elif k % 25 == 0 or k == len(ids):
                print(f"{k}/{len(ids)}  {time.time() - t0:.0f} s  {contagem}", flush=True)
    print(f"\n{contagem}  ({(time.time() - t0) / max(1, len(ids)):.1f} s por texto)")
    _salvar_explicacoes(con)


def _salvar_explicacoes(con) -> None:
    r = explicacao.salvar_cache(con)
    print(f"{r[1]} textos em {r[0]}" if r else "PULSO_EXPLICACOES vazio: nada gravado")


def _imprimir(titulo, d) -> None:
    print(f"== {titulo}")
    print(json.dumps(d, ensure_ascii=False, indent=2, default=str))


def _imprimir_resumo(r) -> None:
    print("== resumo")
    print(f"solicitacoes: {r['solicitacoes']}")
    print(f"eventos: {r['eventos']}")
    print(f"{'fila':5} {'nome':28} {'oficial':>8} {'recomendada':>12}")
    for f in r["filas"]:
        print(f"{f['codigo']:5} {f['nome']:28} {f['oficial']:>8} {f['recomendada']:>12}")
    print(f"pedidos de mudanca: {r['mudancas']}")
    for t, g in r["regra_de_ouro"].items():
        print(f"regra de ouro {t}: {'ok' if g.get('ok') else 'VIOLADA ' + g.get('erro', '')}")


if __name__ == "__main__":
    sys.exit(main())
