import { NavLink, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Activity, ClipboardCheck, LayoutGrid, ListOrdered, LogOut } from 'lucide-react'
import { api } from '../api/cliente'
import type { Resumo } from '../api/tipos'
import { useApi } from '../api/useApi'
import { Marca, cx } from '../components/ui'
import { useAuth } from '../store/auth'

interface ContextoProfissional {
  resumo: Resumo | null
  erroResumo: string | null
  recarregarResumo: () => void
  medicoId: number
}

/** Resumo da API compartilhado pelas telas (contadores do menu, indicadores). */
export const useProfissional = () => useOutletContext<ContextoProfissional>()

export function pedidosPendentes(r: Resumo | null) {
  if (!r) return undefined
  return Object.entries(r.mudancas)
    .filter(([k]) => k.endsWith('/pendente'))
    .reduce((s, [, n]) => s + n, 0)
}

export function ProfissionalLayout() {
  const { sessao, sair } = useAuth()
  const navegar = useNavigate()
  const { dados: resumo, erro: erroResumo, recarregar } = useApi(api.resumo)

  const itens = [
    { para: '/profissional/visao', rotulo: 'Visão geral', icone: LayoutGrid },
    { para: '/profissional/fila', rotulo: 'Fila', icone: ListOrdered },
    { para: '/profissional/revisao', rotulo: 'Revisão humana', icone: ClipboardCheck, contador: pedidosPendentes(resumo) },
    { para: '/pipeline', rotulo: 'Pipeline', icone: Activity },
  ]

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#conteudo"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2"
      >
        Pular para o conteúdo
      </a>
      <header className="sticky top-0 z-30 border-b border-linha bg-white">
        <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <Marca para="/profissional/visao" />
            <span className="hidden rounded bg-nevoa-50 px-2 py-0.5 text-xs font-semibold text-petroleo sm:inline">
              Regulação
            </span>
          </div>
          <div className="flex items-center gap-3 sm:gap-5">
            <div className="text-right leading-tight">
              <p className="text-sm font-semibold text-tinta">
                {sessao?.nome} <span className="hidden font-normal text-tinta-soft sm:inline">· {sessao?.funcao}</span>
              </p>
              <p className="whitespace-nowrap text-[11px] text-tinta-soft sm:text-xs">Acesso registrado conforme a LGPD.</p>
            </div>
            <button
              onClick={() => {
                sair()
                navegar('/')
              }}
              className="grid size-10 place-items-center rounded-lg text-tinta-soft hover:bg-nevoa-50 hover:text-petroleo"
              aria-label="Sair"
              title="Sair"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
        <nav aria-label="Área profissional" className="flex gap-1 overflow-x-auto border-t border-linha px-3 md:hidden">
          {itens.map((i) => (
            <NavLink
              key={i.para}
              to={i.para}
              className={({ isActive }) =>
                cx(
                  'flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-sm font-medium',
                  isActive ? 'border-petroleo text-petroleo' : 'border-transparent text-tinta-soft',
                )
              }
            >
              {i.rotulo}
              {i.contador !== undefined && <Contador n={i.contador} />}
            </NavLink>
          ))}
        </nav>
      </header>

      <div className="flex flex-1">
        <nav aria-label="Área profissional" className="hidden w-60 shrink-0 border-r border-linha bg-white/60 px-3 py-6 md:block">
          <ul className="sticky top-22 space-y-1">
            {itens.map((i) => (
              <li key={i.para}>
                <NavLink
                  to={i.para}
                  className={({ isActive }) =>
                    cx(
                      'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                      isActive ? 'bg-petroleo text-white' : 'text-tinta hover:bg-nevoa-50',
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <i.icone size={17} aria-hidden="true" />
                      <span className="flex-1">{i.rotulo}</span>
                      {i.contador !== undefined && <Contador n={i.contador} invertido={isActive} />}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main id="conteudo" className="min-w-0 flex-1">
          <Outlet context={{ resumo, erroResumo, recarregarResumo: recarregar, medicoId: sessao?.medicoId ?? 0 } satisfies ContextoProfissional} />
        </main>
      </div>
    </div>
  )
}

function Contador({ n, invertido }: { n: number; invertido?: boolean }) {
  return (
    <span
      className={cx(
        'tabular min-w-6 rounded-full px-1.5 text-center text-xs font-semibold leading-5',
        n === 0 ? 'bg-linha text-tinta-soft' : invertido ? 'bg-white text-petroleo' : 'bg-prioritario text-white',
      )}
      aria-label={`${n} pendentes`}
    >
      {n}
    </span>
  )
}
