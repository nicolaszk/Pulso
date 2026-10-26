import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { CheckCheck, Square, StepForward } from 'lucide-react'
import { api } from '../../api/cliente'
import { formatarCid, motivoSemPrefixo, ROTULO_MUDANCA } from '../../api/rotulos'
import type { Mudanca, TipoMudanca } from '../../api/tipos'
import { useApi } from '../../api/useApi'
import { ModalDecisao, rotulosDecisao, type Decisao } from '../../components/modais'
import { Paginacao } from '../../components/Paginacao'
import { Botao, Carregando, FalhaApi, SeloFila, cx, useAviso } from '../../components/ui'
import { useProfissional } from '../../layouts/ProfissionalLayout'
import { formatarData, formatarInstante } from '../../lib/datas'

const POR_PAGINA = 12
/** Pausa entre um evento e outro no modo automático, para dar para acompanhar o contador */
const INTERVALO_MS = 120

const FILTROS: ('todos' | TipoMudanca)[] = ['todos', 'subir', 'descer', 'sair']

const BORDA: Record<TipoMudanca, string> = {
  subir: 'border-t-g1',
  descer: 'border-t-g6',
  sair: 'border-t-linha',
}

export function RevisaoHumana() {
  const { resumo, recarregarResumo, medicoId } = useProfissional()
  const avisar = useAviso()
  const { hash } = useLocation()
  const navegar = useNavigate()
  const pendentes = useApi(() => api.mudancas('pendente'))
  const decididas = useApi(() => api.mudancas('todas'))
  const [filtro, setFiltro] = useState<'todos' | TipoMudanca>('todos')
  const [pagina, setPagina] = useState(1)
  const [aberta, setAberta] = useState<{ mudanca: Mudanca; decisao: Decisao } | null>(null)
  // Modo automático: processa eventos um a um até o sistema abrir um pedido novo.
  const [rodando, setRodando] = useState(false)
  const [lidos, setLidos] = useState(0)
  const [restantes, setRestantes] = useState<number | null>(null)
  const parar = useRef(false)
  useEffect(() => () => void (parar.current = true), [])

  // Link vindo da tela do paciente: abre a página do pedido e rola até ele.
  useEffect(() => {
    const id = Number(hash.replace('#pedido-', ''))
    const i = pendentes.dados?.findIndex((m) => m.id === id) ?? -1
    if (i < 0) return
    setFiltro('todos')
    setPagina(Math.floor(i / POR_PAGINA) + 1)
    requestAnimationFrame(() => document.querySelector(hash)?.scrollIntoView({ block: 'center' }))
  }, [hash, pendentes.dados])

  function atualizarTudo() {
    pendentes.recarregar()
    decididas.recarregar()
    recarregarResumo()
  }

  async function processarAteNovoPedido() {
    parar.current = false
    setRodando(true)
    setLidos(0)
    const antes = new Set((pendentes.dados ?? []).map((m) => m.id))
    let n = 0
    let motivo: 'novo' | 'fim' | 'parado' | 'erro' = 'parado'
    try {
      while (!parar.current) {
        const r = await api.processarEventos(1)
        n += r.eventos
        setLidos(n)
        setRestantes(r.pendentes)
        if (r.aberta > 0) {
          motivo = 'novo'
          break
        }
        if (r.eventos === 0 || r.pendentes === 0) {
          motivo = 'fim'
          break
        }
        await new Promise((ok) => setTimeout(ok, INTERVALO_MS))
      }
    } catch (e) {
      motivo = 'erro'
      avisar('Falha ao processar', e instanceof Error ? e.message : undefined)
    }
    setRodando(false)
    atualizarTudo()

    const lidosTexto = `${n} ${n === 1 ? 'evento lido' : 'eventos lidos'}`
    if (motivo === 'novo') {
      // Leva até o pedido que acabou de aparecer
      const novo = (await api.mudancas('pendente').catch(() => [])).find((m) => !antes.has(m.id))
      avisar('Novo pedido na revisão', novo ? `${novo.paciente_nome} · ${lidosTexto}` : lidosTexto)
      if (novo) navegar({ hash: `pedido-${novo.id}` }, { replace: true })
    } else if (motivo === 'fim') {
      avisar('Todos os eventos foram processados', lidosTexto)
    } else if (motivo === 'parado') {
      avisar('Processamento pausado', lidosTexto)
    }
  }

  const lista = (pendentes.dados ?? []).filter((m) => filtro === 'todos' || m.tipo === filtro)
  const totalPaginas = Math.max(1, Math.ceil(lista.length / POR_PAGINA))
  const atual = Math.min(pagina, totalPaginas)
  const visiveis = lista.slice((atual - 1) * POR_PAGINA, atual * POR_PAGINA)

  // Card sem texto pronto: pede ao backend para gerar com o LLM, um de cada vez, só os da página.
  // A chave inclui atualizada_em: um evento novo muda os fatos do pedido e pede outro texto.
  const chave = (m: Mudanca) => `${m.id}:${m.atualizada_em}`
  const [geradas, setGeradas] = useState<Record<string, string>>({})
  const [gerando, setGerando] = useState<string | null>(null)
  const tentadas = useRef(new Set<string>())
  useEffect(() => {
    if (gerando) return
    const falta = visiveis.find((m) => !m.explicacao && !tentadas.current.has(chave(m)))
    if (!falta) return
    const k = chave(falta)
    tentadas.current.add(k)
    setGerando(k)
    api
      .explicacaoMudanca(falta.id)
      .then((r) => r.fonte === 'llm' && setGeradas((g) => ({ ...g, [k]: r.texto })))
      .catch(() => {}) // sem LLM: fica o motivo do motor
      .finally(() => setGerando(null))
  })

  function irPara(n: number) {
    setPagina(n)
    window.scrollTo({ top: 0 })
  }
  const historico = (decididas.dados ?? []).filter((m) => m.status === 'aprovada' || m.status === 'rejeitada')
  const eventosPendentes = rodando && restantes !== null ? restantes : (resumo?.eventos.pendentes ?? 0)

  return (
    <div className="px-4 py-8 sm:px-6 lg:px-10">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-[2.5rem]">Revisão humana</h1>
        {rodando ? (
          <Botao className="min-h-10 px-4" onClick={() => (parar.current = true)} aria-live="polite">
            <span className="size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" />
            Processando… <span className="tabular text-white/75">{lidos} lidos · {eventosPendentes} restantes</span>
            <Square size={13} className="ml-1 fill-current" aria-label="Parar" />
          </Botao>
        ) : (
          <Botao
            variante="secundario"
            className="min-h-10 px-4"
            disabled={eventosPendentes === 0}
            onClick={processarAteNovoPedido}
            title={
              eventosPendentes === 0
                ? 'Todos os eventos clínicos já foram processados.'
                : 'Lê os eventos clínicos um a um e para quando o sistema abrir um novo pedido de mudança. Clique de novo para continuar.'
            }
          >
            <StepForward size={16} /> Processar até novo pedido
            <span className="tabular text-tinta-soft">({eventosPendentes})</span>
          </Botao>
        )}
      </header>

      <div className="mt-5 flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por tipo de pedido">
        {FILTROS.map((f) => {
          const n = f === 'todos' ? pendentes.dados?.length : pendentes.dados?.filter((m) => m.tipo === f).length
          return (
            <button
              key={f}
              onClick={() => {
                setFiltro(f)
                setPagina(1)
              }}
              aria-pressed={filtro === f}
              className={cx(
                'tabular inline-flex min-h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-semibold transition-colors',
                filtro === f ? 'border-petroleo bg-petroleo text-white' : 'border-linha bg-white hover:border-petroleo/40',
              )}
            >
              {f === 'todos' ? 'Todos' : ROTULO_MUDANCA[f]}
              <span className={filtro === f ? 'text-white/70' : 'text-tinta-soft'}>{n ?? '–'}</span>
            </button>
          )
        })}
      </div>

      {pendentes.erro ? (
        <FalhaApi erro={pendentes.erro} aoTentar={pendentes.recarregar} />
      ) : !pendentes.dados ? (
        <Carregando />
      ) : lista.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-linha bg-white px-6 py-14 text-center">
          <CheckCheck size={26} className="mx-auto text-oceano" />
          <p className="mt-3 font-titulo text-2xl text-petroleo">Nada pendente</p>
        </div>
      ) : (
        <>
        <ul className="mt-6 grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          {visiveis.map((m) => {
            const rotulos = rotulosDecisao(m)
            return (
              <li
                key={m.id}
                id={`pedido-${m.id}`}
                className={cx(
                  'anim-subir flex min-w-0 scroll-mt-24 flex-col break-words rounded-xl border border-t-4 border-linha bg-white p-5',
                  BORDA[m.tipo],
                  hash === `#pedido-${m.id}` && 'ring-2 ring-oceano/40',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="text-xs font-semibold text-tinta-soft">
                    {ROTULO_MUDANCA[m.tipo]}
                    {m.oncologico && <span className="text-g1"> · oncológico</span>}
                  </span>
                  <span className="tabular text-xs text-tinta-soft">#{m.id}</span>
                </div>

                <Link
                  to={`/profissional/pacientes/${m.solicitacao_id}`}
                  className="mt-2 font-titulo text-[1.4rem] font-semibold leading-tight text-petroleo hover:underline"
                >
                  {m.paciente_nome}
                </Link>
                <p className="tabular text-xs text-tinta-soft">
                  {m.solicitacao_id} · {m.procedimento}
                </p>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <SeloFila f={m.fila_atual} />
                  <span aria-hidden="true">→</span>
                  {m.fila_proposta ? <SeloFila f={m.fila_proposta} /> : <span className="text-sm font-semibold">saída</span>}
                  {m.posicao_atual && (
                    <span className="tabular ml-1 text-xs text-tinta-soft">
                      posição {m.posicao_atual}
                      {m.posicao_proposta && (
                        <span
                          className="whitespace-nowrap"
                          title="Calculada sobre a fila oficial de hoje, como se só este pedido fosse aprovado. Pedidos parecidos podem cair na mesma posição."
                        >
                          {` → ~${m.posicao_proposta} se aprovado sozinho`}
                        </span>
                      )}
                      {m.posicao_recomendada && (
                        <>
                          {' · '}
                          <span
                            className="whitespace-nowrap"
                            title="Posição na fila recomendada de agora, como se todos os pedidos pendentes fossem aprovados."
                          >
                            {m.posicao_recomendada} com todos aprovados
                          </span>
                        </>
                      )}
                    </span>
                  )}
                </div>

                <p className="mt-3 text-sm leading-relaxed">
                  {m.explicacao || geradas[chave(m)] || motivoSemPrefixo(m.motivo)}
                </p>
                {gerando === chave(m) && (
                  <p className="mt-1 text-xs text-tinta-soft" aria-live="polite">
                    Gerando explicação em linguagem clara…
                  </p>
                )}

                {m.evidencias.some((e) => e.trecho) && (
                  <ul className="mt-3 space-y-1.5 rounded-lg bg-nevoa-50 px-3.5 py-2.5 text-[13px]">
                    {m.evidencias
                      .filter((e) => e.trecho)
                      .map((e, i) => (
                        <li key={i}>
                          <span className="text-tinta-soft">
                            {e.data ? formatarData(e.data) : 'texto'} · {e.origem}:{' '}
                          </span>
                          {e.trecho?.replace(/\bCID C(\d{2,3})\b/, (_, c) => `CID ${formatarCid('C' + c)}`)}
                        </li>
                      ))}
                  </ul>
                )}

                <div className="mt-auto flex flex-col gap-2 pt-4 sm:flex-row sm:justify-end">
                  <Botao variante="secundario" className="min-h-10 px-4" onClick={() => setAberta({ mudanca: m, decisao: 'rejeitar' })}>
                    {rotulos.rejeitar}
                  </Botao>
                  <Botao className="min-h-10 px-4" onClick={() => setAberta({ mudanca: m, decisao: 'aprovar' })}>
                    {rotulos.aprovar}
                  </Botao>
                </div>
              </li>
            )
          })}
        </ul>
        <Paginacao className="mt-5" atual={atual} porPagina={POR_PAGINA} totalItens={lista.length} aoMudar={irPara} />
        </>
      )}

      {historico.length > 0 && (
        <section className="mt-12">
          <h2 className="text-2xl">Decididos</h2>
          <ul className="mt-3 divide-y divide-linha rounded-xl border border-linha bg-white">
            {historico.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm">
                <Link to={`/profissional/pacientes/${m.solicitacao_id}`} className="font-semibold hover:text-petroleo hover:underline">
                  {m.paciente_nome}
                </Link>
                <span className="text-tinta-soft">
                  {m.status === 'aprovada'
                    ? `${m.fila_atual} → ${m.fila_proposta ?? 'saída'}`
                    : `mantido em ${m.fila_atual}`}{' '}
                  · {m.medico_nome}
                  {m.decidida_em && ` · ${formatarInstante(m.decidida_em)}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <ModalDecisao
        mudanca={aberta?.mudanca ?? null}
        decisao={aberta?.decisao ?? 'aprovar'}
        medicoId={medicoId}
        aoFechar={() => setAberta(null)}
        aoDecidir={(m, r) => {
          avisar(
            'Decisão registrada',
            r.status === 'aprovada' && r.de && r.para
              ? `${m.paciente_nome}: posição ${r.de.posicao_final} → ${r.para.posicao_final}.`
              : r.status === 'aprovada'
                ? `${m.paciente_nome} saiu da fila.`
                : `${m.paciente_nome}: nível mantido.`,
          )
          atualizarTudo()
        }}
      />
    </div>
  )
}
