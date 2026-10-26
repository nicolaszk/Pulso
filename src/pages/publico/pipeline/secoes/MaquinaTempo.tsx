// 05 · Máquina do tempo: o log de eventos rebobinado, o motor reavaliando cada paciente a cada evento.
// Dados de dados/maquina_tempo.json (scripts/dados_maquina_tempo.py, módulo fila_cirurgica/maquina_tempo).
import { useRef, type ReactNode } from 'react'
import { SeloFila } from '../../../../components/ui'
import type { FilaCodigo } from '../../../../data/fila'
import { COR_NIVEL } from '../dados'
import mt from '../dados/maquina_tempo.json'
import { br, useVisto } from '../rolagem'

const P = mt.promocoes
const H = mt.heroi

const SALTOS = Object.entries(P.saltos).map(([s, n]) => {
  const [de, para] = s.split('->') as [FilaCodigo, FilaCodigo]
  return { de, para, n }
})
const MAIOR_SALTO = Math.max(...SALTOS.map((s) => s.n))

// Dias desde a 1ª promoção, em faixas de 30 dias; a última junta tudo acima de 180.
const FAIXAS = [30, 60, 90, 120, 150, 180, Infinity]
const HISTO = FAIXAS.map((fim, i) => {
  const ini = i ? FAIXAS[i - 1] : 0
  return {
    rotulo: fim === Infinity ? `>${ini}` : `${ini + (i ? 1 : 0)}–${fim}`,
    n: P.dias_todos.filter((d) => d > ini && d <= fim).length,
  }
})
const MAIOR_FAIXA = Math.max(...HISTO.map((f) => f.n))

const EVENTO: Record<string, string> = {
  'biopsia/positivo': 'Biópsia positiva',
  'consulta_reavaliacao/piora': 'Reavaliação com piora',
}
const PRIORIDADE: Record<string, string> = { baixa: 'baixa', media: 'média', alta: 'alta', nao_informada: 'não informada' }
const dataBr = (iso: string) => iso.split('-').reverse().join('/')

export function MaquinaTempo() {
  const ref = useRef<HTMLElement>(null)
  const visto = useVisto(ref)

  const numeros = [
    { v: P.n, t: `pacientes subiram de nível durante a espera, de ${br(mt.ativas)} ativos` },
    { v: P.baixa_ou_media, t: 'deles tinham prioridade manual baixa ou média' },
    { v: P.de_g6_g7, t: 'entraram na fila como G6 ou G7' },
    { v: P.dias.mediana, t: `dias, mediana, desde a 1ª subida (p25 ${P.dias.p25} · p75 ${P.dias.p75})` },
  ]

  return (
    <section
      ref={ref}
      id="maquina-tempo"
      className="relative py-20 md:py-28"
      data-traco="duas"
      aria-labelledby="pl-maquina-tempo"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <p className="pl-num">05 · Máquina do tempo</p>
        <h2 id="pl-maquina-tempo" className="text-[2.25rem] sm:text-[2.75rem]">
          O histórico, reprocessado evento a evento.
        </h2>
        <p className="mt-3 max-w-2xl text-[16px] text-tinta-soft">
          O módulo <code className="pl-mono text-[14px]">maquina_tempo</code> rebobina o log de eventos e reavalia cada
          solicitação ativa a cada evento novo, só com os eventos até aquela data. Mesmo motor da produção, sem banco e sem
          tocar na fila oficial. Data de referência: {dataBr(mt.data_referencia)}.
        </p>

        <dl className="mt-10 grid grid-cols-2 gap-x-6 gap-y-6 border-y border-linha py-6 lg:grid-cols-4">
          {numeros.map((n) => (
            <div key={n.t}>
              <dt className="sr-only">{n.t}</dt>
              <dd className="tabular font-titulo text-4xl font-bold text-petroleo">{br(n.v)}</dd>
              <dd className="mt-1 text-[13px] leading-snug text-tinta-soft">{n.t}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-10 grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="rounded-xl border border-linha bg-white p-4 sm:p-5">
            <p className="pl-rotulo">Nível de entrada → nível depois dos eventos</p>
            <ul className="space-y-2">
              {SALTOS.map((s, i) => (
                <li key={`${s.de}${s.para}`} className="grid grid-cols-[7.5rem_minmax(0,1fr)_2.5rem] items-center gap-3">
                  <span className="flex items-center gap-1.5">
                    <SeloFila f={s.de} compacto />
                    <span aria-hidden="true" className="text-tinta-soft">→</span>
                    <SeloFila f={s.para} compacto />
                  </span>
                  <span className="h-2.5 rounded-sm bg-nevoa-50">
                    <span
                      className="block h-full rounded-sm transition-[width] duration-700 ease-out motion-reduce:transition-none"
                      style={{
                        width: visto ? `${(s.n / MAIOR_SALTO) * 100}%` : 0,
                        background: COR_NIVEL[s.para].cor,
                        transitionDelay: `${i * 40}ms`,
                      }}
                    />
                  </span>
                  <span className="tabular text-right text-[14px] font-semibold text-tinta">{s.n}</span>
                </li>
              ))}
            </ul>

            <p className="pl-rotulo mt-8">Dias desde a 1ª subida · {P.n} pacientes</p>
            <div className="grid h-28 grid-cols-7 items-end gap-2" role="img" aria-label={HISTO.map((f) => `${f.rotulo} dias: ${f.n}`).join('; ')}>
              {HISTO.map((f, i) => (
                <div key={f.rotulo} className="flex h-full flex-col justify-end">
                  <span className="tabular mb-1 text-center text-[12px] font-semibold text-tinta">{f.n}</span>
                  <span
                    className="block rounded-t-sm bg-oceano transition-[height] duration-700 ease-out motion-reduce:transition-none"
                    style={{ height: visto ? `${(f.n / MAIOR_FAIXA) * 72}%` : 0, transitionDelay: `${i * 50}ms` }}
                  />
                </div>
              ))}
            </div>
            <div className="mt-1.5 grid grid-cols-7 gap-2 border-t border-linha pt-1.5">
              {HISTO.map((f) => (
                <span key={f.rotulo} className="tabular whitespace-nowrap text-center text-[10px] text-tinta-soft sm:text-[11px]">
                  {f.rotulo}
                </span>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-linha bg-white p-4 sm:p-5">
            <p className="pl-rotulo">{H.solicitacao_id} · a 621, no replay</p>
            <ol className="relative ml-1.5 border-l-2 border-linha">
              <Marco data="entrada" fila={H.fila_entrada as FilaCodigo}>
                Só o cadastro. Prioridade manual: {PRIORIDADE[H.prioridade_manual]}.
              </Marco>
              {H.transicoes.map((t, i) => (
                <Marco key={t.data} data={dataBr(t.data)} fila={t.para as FilaCodigo}>
                  {EVENTO[t.evento] ?? t.evento}: {t.de} → {t.para}.
                  {i === 0 && (
                    <>
                      {' '}
                      Posição {H.primeira_promocao.posicao} de {br(H.primeira_promocao.total)} na fila de prioridades.
                    </>
                  )}
                </Marco>
              ))}
              <Marco data={dataBr(H.hoje.data)} fila={H.hoje.fila as FilaCodigo}>
                Posição {H.hoje.posicao} de {br(H.hoje.total)}. Primeira subida há{' '}
                {Math.round((Date.parse(H.hoje.data) - Date.parse(H.primeira_promocao.data)) / 864e5)} dias.
              </Marco>
            </ol>

            <p className="pl-rotulo mt-8">Marcações do motor na data de referência</p>
            <ul className="tabular space-y-1.5 text-[14px] text-tinta">
              <li>
                <b>{mt.consistencia.oncologico_prioridade_baixa}</b> com CID C* e prioridade manual baixa (
                {mt.consistencia.oncologico_prioridade_media} com média)
              </li>
              <li>
                <b>{mt.consistencia.biopsia_positiva_cid_nao_oncologico}</b> com biópsia positiva e CID ainda não oncológico
              </li>
              <li>
                <b>{mt.consistencia.prazo_estourado}</b> com o prazo do nível estourado
              </li>
            </ul>
          </div>
        </div>

        <p className="mt-6 max-w-3xl text-[13px] text-tinta-soft">
          Antecipação: dos {mt.antecipacao.n_agudos} pacientes que foram ao PS ou internados durante a espera,{' '}
          {mt.antecipacao.n_com_sinal} tinham um sinal clínico registrado antes (mediana de {mt.antecipacao.dias.mediana}{' '}
          dias). Amostra pequena; não é a métrica principal. Reproduzir:{' '}
          <code className="pl-mono rounded bg-nevoa-50 px-1.5 py-0.5 text-tinta">python -m maquina_tempo</code> ou{' '}
          <code className="pl-mono whitespace-nowrap rounded bg-nevoa-50 px-1.5 py-0.5 text-tinta">GET /maquina-tempo</code>.
        </p>
      </div>
    </section>
  )
}

function Marco({ data, fila, children }: { data: string; fila: FilaCodigo; children: ReactNode }) {
  return (
    <li className="relative pb-5 pl-5 last:pb-0">
      <span
        aria-hidden="true"
        className="absolute -left-[7px] top-1 size-3 rounded-full ring-2 ring-white"
        style={{ background: COR_NIVEL[fila].cor }}
      />
      <span className="flex flex-wrap items-center gap-2">
        <span className="pl-mono text-[12px] text-tinta-soft">{data}</span>
        <SeloFila f={fila} compacto />
      </span>
      <p className="mt-1 text-[14px] text-tinta">{children}</p>
    </li>
  )
}
