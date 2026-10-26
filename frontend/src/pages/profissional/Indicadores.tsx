import { Link } from 'react-router-dom'
import type { Resumo } from '../../api/tipos'
import { cx } from '../../components/ui'
import { pedidosPendentes } from '../../layouts/ProfissionalLayout'

export function Indicadores({ resumo }: { resumo: Resumo }) {
  const itens = [
    { valor: resumo.solicitacoes.ativa ?? 0, rotulo: 'ativas', link: '/profissional/fila', tom: 'text-petroleo' },
    { valor: resumo.prazo_estourado, rotulo: 'prazo estourado', link: '/profissional/fila?ordem=dias&dir=desc', tom: 'text-g1' },
    { valor: pedidosPendentes(resumo) ?? 0, rotulo: 'revisão humana', link: '/profissional/revisao', tom: 'text-g3' },
  ]

  return (
    <div className="mt-6 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-linha bg-linha">
      {itens.map((i) => (
        <Link key={i.rotulo} to={i.link} className="bg-white px-5 py-4 transition-colors hover:bg-nevoa-50 sm:px-6">
          <p className={cx('tabular font-titulo text-[2.2rem] font-semibold leading-none', i.tom)}>{i.valor}</p>
          <p className="mt-1.5 text-[13px] text-tinta-soft">{i.rotulo}</p>
        </Link>
      ))}
    </div>
  )
}
