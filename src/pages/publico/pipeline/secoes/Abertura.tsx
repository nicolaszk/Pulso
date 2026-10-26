// Abertura: o mapa do pipeline. Cada etapa leva à sua seção.
import type { CSSProperties } from 'react'
import { Activity, Database, History, ListOrdered, ReceiptText, Stamp, type LucideIcon } from 'lucide-react'

interface Etapa {
  alvo: string
  titulo: string
  metrica: string
  rotulo: string
  icone: LucideIcon
}

const ETAPAS: Etapa[] = [
  { alvo: 'limpeza', titulo: 'Entrada e limpeza', metrica: '941 → 902', rotulo: 'pedidos ativos', icone: Database },
  { alvo: 'motor', titulo: 'Motor em 8 níveis', metrica: 'G1a → G7', rotulo: 'ordem fixa entre os níveis', icone: ListOrdered },
  { alvo: 'eventos', titulo: 'Eventos por data', metrica: '1.489 → 128', rotulo: 'eventos → pedidos pendentes', icone: Activity },
  { alvo: 'medico', titulo: 'Decisão do médico', metrica: 'aprova ou rejeita', rotulo: 'a fila oficial só muda se aprovar', icone: Stamp },
  { alvo: 'maquina-tempo', titulo: 'Máquina do tempo', metrica: '123', rotulo: 'subiram de nível no replay', icone: History },
  { alvo: 'saida', titulo: 'Fila com recibos', metrica: '897', rotulo: 'posições com justificativa', icone: ReceiptText },
]

// Uma batida de ECG centrada em cada coluna (viewBox 0..100 por coluna); a linha de base é contínua entre elas.
const BATIDA = 'l3 -5 l3 5 l5 0 l2 7 l3 -34 l3 40 l2.5 -13 l7 0 l4 -7 l4 7'
const TRACO = `M0 40 L34 40 ${BATIDA} L100 40` // pico (R) em x = 50

function irPara(alvo: string) {
  document.getElementById(alvo)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

export function Abertura() {
  return (
    <section className="mx-auto max-w-6xl px-4 pb-16 pt-12 sm:px-6 md:pb-24 md:pt-20" aria-labelledby="pipeline-titulo">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-oceano">Pipeline de priorização</p>
      <h1 id="pipeline-titulo" className="mt-4 max-w-4xl text-[2.5rem] sm:text-6xl lg:text-7xl">
        Como a fila recomendada é montada
      </h1>
      <p className="mt-6 max-w-2xl text-[17px] text-tinta-soft">
        Entram 941 pedidos de cirurgia e 1.505 eventos clínicos. Sai uma fila de 897 posições em oito níveis, cada
        uma com a justificativa do motor. Uma mudança de nível só vale na fila oficial depois que um médico aprova.
      </p>

      {/* as colunas seguem ETAPAS: uma entrada nova ganha coluna, número e batida */}
      <ol
        className="pl-etapas mt-10 grid gap-2 md:mt-14 md:gap-3"
        style={{ '--etapas': ETAPAS.length } as CSSProperties}
      >
        {ETAPAS.map((e, i) => (
          <li key={e.alvo} className="flex flex-col">
            <svg className="pl-abertura-traco hidden md:block" viewBox="0 0 100 64" preserveAspectRatio="none" aria-hidden="true">
              <path d={TRACO} pathLength={1} style={{ animationDelay: `${200 + i * 500}ms` }} />
            </svg>
            <button
              type="button"
              onClick={() => irPara(e.alvo)}
              className="anim-subir group grid h-full w-full grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-x-3 rounded-xl border border-linha bg-white px-4 py-3 text-left transition-colors hover:border-petroleo/40 md:mt-2 md:flex md:flex-col md:items-stretch md:p-4"
              style={{ animationDelay: `${180 + i * 120}ms` }}
            >
              <span className="flex items-center justify-between">
                <span className="font-titulo text-2xl font-semibold leading-none text-agua md:text-3xl" aria-hidden="true">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="hidden size-9 place-items-center rounded-lg bg-nevoa-50 text-oceano md:grid">
                  <e.icone size={18} />
                </span>
              </span>
              <span className="flex min-w-0 flex-col md:mt-4">
                <span className="text-sm font-semibold text-tinta group-hover:text-petroleo">{e.titulo}</span>
                <span className="tabular font-titulo text-lg font-bold leading-snug text-petroleo md:mt-1 md:text-xl">{e.metrica}</span>
                <span className="text-[13px] text-tinta-soft md:mt-0.5">{e.rotulo}</span>
              </span>
              <span className="grid size-9 place-items-center rounded-lg bg-nevoa-50 text-oceano md:hidden">
                <e.icone size={18} />
              </span>
            </button>
          </li>
        ))}
      </ol>
      <p className="mt-6 text-[13px] text-tinta-soft">
        Dados sintéticos do desafio. Todos os números saem da execução do pipeline no dataset completo.
      </p>
    </section>
  )
}
