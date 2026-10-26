import type { ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cx } from './ui'

/** Números de página com reticências: 1 … 4 5 6 … 20 */
function paginas(atual: number, total: number): (number | null)[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const set = new Set([1, total, atual - 1, atual, atual + 1].filter((n) => n >= 1 && n <= total))
  const lista = [...set].sort((a, b) => a - b)
  return lista.flatMap((n, i) => (i > 0 && n - lista[i - 1] > 1 ? [null, n] : [n]))
}

export function Paginacao({
  atual,
  porPagina,
  totalItens,
  aoMudar,
  className,
}: {
  atual: number
  porPagina: number
  totalItens: number
  aoMudar: (pagina: number) => void
  className?: string
}) {
  const total = Math.max(1, Math.ceil(totalItens / porPagina))
  if (totalItens === 0) return null
  return (
    <nav aria-label="Paginação" className={cx('flex flex-wrap items-center justify-between gap-3 text-sm', className)}>
      <p className="tabular text-tinta-soft">
        {(atual - 1) * porPagina + 1}–{Math.min(atual * porPagina, totalItens)} de {totalItens}
      </p>
      {total > 1 && (
        <div className="flex items-center gap-1">
          <BotaoPagina rotulo="Página anterior" desativado={atual === 1} aoClicar={() => aoMudar(atual - 1)}>
            <ChevronLeft size={17} />
          </BotaoPagina>
          {paginas(atual, total).map((n, i) =>
            n === null ? (
              <span key={`r${i}`} className="px-1 text-tinta-soft">
                …
              </span>
            ) : (
              <button
                key={n}
                onClick={() => aoMudar(n)}
                aria-current={n === atual ? 'page' : undefined}
                className={cx(
                  'tabular min-w-9 rounded-md px-2 py-1.5 font-medium',
                  n === atual ? 'bg-petroleo text-white' : 'hover:bg-nevoa-50',
                )}
              >
                {n}
              </button>
            ),
          )}
          <BotaoPagina rotulo="Próxima página" desativado={atual === total} aoClicar={() => aoMudar(atual + 1)}>
            <ChevronRight size={17} />
          </BotaoPagina>
        </div>
      )}
    </nav>
  )
}

function BotaoPagina({
  rotulo,
  desativado,
  aoClicar,
  children,
}: {
  rotulo: string
  desativado: boolean
  aoClicar: () => void
  children: ReactNode
}) {
  return (
    <button
      onClick={aoClicar}
      disabled={desativado}
      aria-label={rotulo}
      className="grid size-9 place-items-center rounded-md hover:bg-nevoa-50 disabled:opacity-35 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  )
}
