import { Link } from 'react-router-dom'
import { api } from '../../api/cliente'
import { useApi } from '../../api/useApi'
import { Carregando, Cartao, FalhaApi, SeloFila, TOM_FILA, cx } from '../../components/ui'
import { NOME_FILA } from '../../data/fila'
import { rotuloMarcacao } from '../../data/revisao'
import { useProfissional } from '../../layouts/ProfissionalLayout'
import { formatarData, HOJE } from '../../lib/datas'
import { Indicadores } from './Indicadores'

export function VisaoGeral() {
  const { resumo, erroResumo, recarregarResumo } = useProfissional()
  const altas = useApi(() => api.marcacoes('alta'))

  return (
    <div className="px-4 py-8 sm:px-6 lg:px-10">
      <header>
        <p className="tabular text-sm text-tinta-soft">{formatarData(HOJE)}</p>
        <h1 className="text-[2.5rem]">Visão geral</h1>
      </header>

      {erroResumo ? (
        <FalhaApi erro={erroResumo} aoTentar={recarregarResumo} />
      ) : !resumo ? (
        <Carregando />
      ) : (
        <>
          <Indicadores resumo={resumo} />

          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
            <Cartao className="p-6">
              <h2 className="text-2xl">Distribuição por nível</h2>
              <ul className="mt-5 space-y-2.5">
                {resumo.filas.map(({ codigo: f, oficial: n }) => {
                  const maior = Math.max(...resumo.filas.map((x) => x.oficial))
                  return (
                    <li key={f}>
                      <Link
                        to={`/profissional/fila?nivel=${f}`}
                        className="-mx-2 grid grid-cols-[3.25rem_minmax(0,1fr)_2.5rem] items-center gap-3 rounded-md px-2 py-1 hover:bg-areia sm:grid-cols-[3.25rem_12rem_minmax(0,1fr)_2.5rem]"
                      >
                        <SeloFila f={f} compacto />
                        <span className="hidden truncate text-sm sm:block">{NOME_FILA[f]}</span>
                        <span className="h-2 overflow-hidden rounded-full bg-nevoa-50" aria-hidden="true">
                          <span className={cx('block h-full rounded-full', TOM_FILA[f].barra)} style={{ width: `${(n / maior) * 100}%` }} />
                        </span>
                        <span className="tabular text-right text-sm font-semibold">{n}</span>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </Cartao>

            <Cartao className="p-6">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-2xl">Precisa de olho humano</h2>
                {altas.dados && <span className="tabular text-sm text-tinta-soft">{altas.dados.length}</span>}
              </div>
              {altas.erro ? (
                <FalhaApi erro={altas.erro} aoTentar={altas.recarregar} />
              ) : !altas.dados ? (
                <Carregando />
              ) : (
                <ul className="-mx-2 mt-4 max-h-[26rem] divide-y divide-linha overflow-y-auto overflow-x-hidden">
                  {altas.dados.map((m) => (
                    <li key={m.solicitacao_id + m.marcacao}>
                      <Link
                        to={`/profissional/pacientes/${m.solicitacao_id}`}
                        className="flex items-start gap-3 rounded-md px-2 py-3 hover:bg-areia"
                      >
                        <span className="mt-2 size-2 shrink-0 rounded-full bg-g1" aria-hidden="true" />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-semibold">{m.paciente_nome}</span>
                          <span className="block text-[13px] text-tinta-soft">{rotuloMarcacao(m.marcacao)}</span>
                        </span>
                        <SeloFila f={m.fila} compacto />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Cartao>
          </div>
        </>
      )}
    </div>
  )
}
