// Peças da cena do médico: o pedido #121 e os carimbos.
import type { CSSProperties, ReactNode } from 'react'
import { SeloFila, cx } from '../../../components/ui'

export type Decisao = 'aprovar' | 'rejeitar'

// Evidências do pedido #121 como estão no banco (texto do evento, sem retoque).
const EVIDENCIAS = [
  { data: '20/09/2026', origem: 'laboratório de patologia', trecho: 'Biopsia: carcinoma epidermoide invasor.' },
  { data: '09/10/2026', origem: 'ambulatório', trecho: 'AP positivo para malignidade. Necessario atualizar CID e prioridade.' },
]

export function CartaoPedido({
  marca,
  motivo,
  digitando,
  className,
  children,
}: {
  /** impressão do carimbo no papel */
  marca?: Decisao | null
  /** motivo da rejeição, se houver */
  motivo?: string
  /** cursor piscando no fim do motivo */
  digitando?: boolean
  className?: string
  children?: ReactNode
}) {
  return (
    <article
      aria-label="Pedido de mudança #121"
      className={cx('relative rounded-xl border border-linha bg-white p-5 shadow-[0_18px_40px_-28px_rgba(4,58,70,0.45)]', className)}
    >
      <header className="pl-mono flex flex-wrap justify-between gap-2 border-b border-dashed border-linha pb-3 text-[11.5px] uppercase tracking-[0.08em] text-tinta-soft">
        <span>Pedido #121 · subir</span>
        <span>SOL-2026-00610</span>
      </header>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <SeloFila f="G6" compacto />
        <span aria-hidden="true" className="text-tinta-soft">→</span>
        <SeloFila f="G1a" compacto />
        <span className="tabular ml-auto font-titulo text-lg font-bold text-petroleo">posição 621 → 16</span>
      </div>
      <p className="mt-2 text-[13px] text-tinta-soft">Histerectomia · mulher, 61 anos · CID D25.9 (mioma)</p>
      <ul className="mt-3 space-y-2.5">
        {EVIDENCIAS.map((e) => (
          <li key={e.data}>
            <span className="pl-mono block text-[11px] text-tinta-soft">
              {e.data} · {e.origem}
            </span>
            <q className="pl-mono text-[12.5px] text-tinta">{e.trecho}</q>
          </li>
        ))}
      </ul>
      {motivo != null && (
        <p className="pl-mono mt-3 rounded-lg border border-dashed border-urgente/50 px-3 py-2 text-[12.5px]">
          <span className="block text-[10.5px] uppercase tracking-[0.08em] text-tinta-soft">motivo da rejeição</span>
          {motivo}
          {digitando && <i className="pl-cursor" aria-hidden="true" />}
        </p>
      )}
      {children}
      {marca && (
        <span className={cx('pl-marca', marca)} aria-hidden="true">
          {marca === 'aprovar' ? 'Aprovado' : 'Rejeitado'}
        </span>
      )}
    </article>
  )
}

export function Carimbo({
  tipo,
  onClick,
  estilo,
  ativo,
}: {
  tipo: Decisao
  onClick?: () => void
  estilo?: CSSProperties
  ativo?: boolean
}) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      className={cx('pl-carimbo', tipo)}
      style={estilo}
      onClick={onClick}
    >
      {tipo === 'aprovar' ? 'Aprovar' : 'Rejeitar'}
    </button>
  )
}
