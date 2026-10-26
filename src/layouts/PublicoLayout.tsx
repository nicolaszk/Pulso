import { Link, NavLink, Outlet } from 'react-router-dom'
import { Marca, cx } from '../components/ui'

export function PublicoLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#conteudo"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2"
      >
        Pular para o conteúdo
      </a>
      <header className="border-b border-linha bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <Marca />
          <nav aria-label="Principal" className="flex items-center gap-1 sm:gap-3">
            <NavLink
              to="/como-funciona"
              className={({ isActive }) =>
                cx(
                  'rounded-md px-2.5 py-2 text-sm font-medium transition-colors hover:text-petroleo',
                  isActive ? 'text-petroleo underline decoration-agua decoration-2 underline-offset-[6px]' : 'text-tinta',
                )
              }
            >
              Como funciona
            </NavLink>
            <Link
              to="/profissional/entrar"
              className="rounded-lg border border-linha px-3 py-2 text-[13px] font-medium text-tinta-soft transition-colors hover:border-petroleo/40 hover:text-petroleo"
            >
              Acesso profissional
            </Link>
          </nav>
        </div>
      </header>

      <main id="conteudo" className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-linha">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-6 text-[13px] text-tinta-soft sm:flex-row sm:justify-between sm:px-6">
          <p>
            <span className="font-semibold text-petroleo">Pulso</span> · Regulação de cirurgias eletivas
          </p>
          <p>Em caso de piora dos sintomas, procure sua unidade de saúde.</p>
        </div>
      </footer>
    </div>
  )
}
