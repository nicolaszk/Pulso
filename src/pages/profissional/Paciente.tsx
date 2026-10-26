import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BedDouble,
  CalendarX,
  CircleAlert,
  FlaskConical,
  Microscope,
  Phone,
  PhoneCall,
  ScanLine,
  Stethoscope,
} from 'lucide-react'
import { api } from '../../api/cliente'
import {
  eventoDePiora,
  formatarCid,
  motivoSemPrefixo,
  partesJustificativa,
  ROTULO_EVENTO,
  ROTULO_MUDANCA,
  ROTULO_PENDENCIA,
  rotuloResultado,
} from '../../api/rotulos'
import type { Detalhe, EventoApi, Evidencia } from '../../api/tipos'
import { useApi } from '../../api/useApi'
import { Carregando, Cartao, FalhaApi, SeloFila, SeloSeveridade, cx } from '../../components/ui'
import { ORDEM_FILAS } from '../../data/fila'
import { rotuloMarcacao } from '../../data/revisao'
import { formatarData, formatarInstante } from '../../lib/datas'

export function Paciente() {
  const { id = '' } = useParams()
  const { dados: d, erro, recarregar } = useApi(() => api.solicitacao(id), [id])

  if (erro) {
    return (
      <div className="px-4 py-8 sm:px-6 lg:px-10">
        <Voltar />
        {erro === 'solicitacao nao encontrada' ? (
          <p className="mt-8 text-sm text-tinta-soft">A solicitação {id} não foi encontrada.</p>
        ) : (
          <FalhaApi erro={erro} aoTentar={recarregar} />
        )}
      </div>
    )
  }
  if (!d) {
    return (
      <div className="px-4 py-8 sm:px-6 lg:px-10">
        <Voltar />
        <Carregando />
      </div>
    )
  }

  const fo = d.fila_oficial
  const pendente = d.mudancas.find((m) => m.status === 'pendente')
  const delta = fo ? fo.posicao_inicial - fo.posicao : 0
  const divergente =
    fo &&
    ((d.prioridade_regulacao === 'baixa' && ORDEM_FILAS.indexOf(fo.fila) <= 3) ||
      (d.prioridade_regulacao === 'alta' && ORDEM_FILAS.indexOf(fo.fila) >= 6))

  return (
    <div className="px-4 py-8 sm:px-6 lg:px-10">
      <Voltar />

      <header className="mt-5 flex flex-col gap-6 border-b border-linha pb-7 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="tabular text-sm text-tinta-soft">
            {d.id} · {d.paciente.id} · {d.paciente.idade} anos · {d.paciente.municipio}
          </p>
          <h1 className="mt-1 text-[2.5rem] sm:text-5xl">{d.paciente.nome}</h1>
          <p className="mt-2 text-[15px]">
            {d.procedimento} · {d.especialidade}
          </p>
          <p className="mt-0.5 text-sm text-tinta-soft">
            <span className="font-semibold text-tinta">{formatarCid(d.cid_principal)}</span> {d.cid_descricao}
          </p>
        </div>
        {fo ? (
          <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
            <div>
              <p className="text-[13px] text-tinta-soft">Posição</p>
              <p className="tabular font-titulo text-5xl font-semibold leading-none text-petroleo">{fo.posicao}</p>
              {delta !== 0 && (
                <p className="tabular mt-1 text-xs text-tinta-soft">
                  {delta > 0 ? '↑' : '↓'} era {fo.posicao_inicial}
                </p>
              )}
            </div>
            <div>
              <p className="mb-1.5 text-[13px] text-tinta-soft">Nível</p>
              <SeloFila f={fo.fila} nome />
              <p className="mt-1 text-xs text-tinta-soft">
                Manual: {d.prioridade_regulacao ?? 'não informada'}
                {divergente && <span className="font-semibold text-g3"> · divergente</span>}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm font-semibold text-tinta-soft">
            Fora da fila{d.motivo_status ? `: ${d.motivo_status}` : ''}
          </p>
        )}
      </header>

      {pendente && (
        <div className="mt-6 flex flex-col gap-3 rounded-xl border border-g3/30 bg-g3-50 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <CircleAlert size={19} className="mt-0.5 shrink-0 text-g3" />
            <p className="text-sm">
              <span className="font-semibold text-g3">
                {ROTULO_MUDANCA[pendente.tipo]}
                {pendente.fila_proposta && ` · ${pendente.fila_atual} → ${pendente.fila_proposta}`}.
              </span>{' '}
              {motivoSemPrefixo(pendente.motivo)}
            </p>
          </div>
          <Link
            to={`/profissional/revisao#pedido-${pendente.id}`}
            className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-petroleo hover:underline"
          >
            Revisar <ArrowRight size={15} />
          </Link>
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="space-y-6">
          <PorQue d={d} />
          <Cartao className="p-6">
            <h2 className="text-[1.75rem]">Justificativa médica</h2>
            <blockquote className="mt-4 border-l-2 border-bege pl-4 text-[15px] leading-relaxed">
              {d.justificativa_clinica}
            </blockquote>
            {d.observacoes && <p className="mt-4 text-sm text-tinta-soft">{d.observacoes}</p>}
            <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-linha pt-4 text-sm sm:grid-cols-4">
              <Dado termo="Dor (EVA)" valor={d.intensidade_dor_eva ?? '—'} />
              <Dado termo="Limitação" valor={d.limitacao_funcional ?? '—'} />
              <Dado termo="Entrada" valor={formatarData(d.data_entrada_fila)} />
              <Dado termo="Comorbidades" valor={d.paciente.comorbidades.join(', ') || 'nenhuma'} />
            </dl>
          </Cartao>
        </div>
        <div className="space-y-6">
          <Sinalizacoes d={d} />
          <LinhaDoTempo eventos={d.eventos} />
          <Historico d={d} />
        </div>
      </div>
    </div>
  )
}

/** Volta para a tela de onde o médico veio (fila, revisão, pendências...); sem histórico, vai para a fila. */
function Voltar() {
  const navegar = useNavigate()
  const temHistorico = (window.history.state as { idx?: number } | null)?.idx
  return (
    <button
      onClick={() => (temHistorico ? navegar(-1) : navegar('/profissional/fila'))}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-petroleo hover:underline"
    >
      <ArrowLeft size={15} /> Voltar
    </button>
  )
}

function Dado({ termo, valor }: { termo: string; valor: string | number }) {
  return (
    <div>
      <dt className="text-xs text-tinta-soft">{termo}</dt>
      <dd className="mt-0.5 font-medium">{valor}</dd>
    </div>
  )
}

/* Por que está nesta posição ---------------------------------------- */

function PorQue({ d }: { d: Detalhe }) {
  const explicacao = useApi(() => api.explicacaoSolicitacao(d.id), [d.id])
  const em = d.estado_motor
  const j = d.fila_oficial ? partesJustificativa(d.fila_oficial.justificativa) : null
  const evidencias = em ? Object.values(em.evidencias).flat() : []

  return (
    <Cartao className="p-6">
      <h2 className="text-[1.75rem]">Por que está nesta posição?</h2>
      {explicacao.dados?.fonte === 'llm' && (
        <p className="mt-4 text-[15px] leading-relaxed">{explicacao.dados.texto}</p>
      )}
      {j && (
        <ul className="mt-4 space-y-1.5 text-[15px]">
          {j.motivos.map((m) => (
            <li key={m} className="flex gap-2">
              <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-oceano" aria-hidden="true" />
              {m}
            </li>
          ))}
        </ul>
      )}
      {em && (
        <dl className="mt-5 grid grid-cols-3 gap-4 border-t border-linha pt-4 text-sm">
          <Dado termo="Data limite" valor={formatarData(em.data_limite_efetiva)} />
          <Dado termo="Sinais" valor={em.n_sinais} />
          <Dado termo="Dor" valor={em.dor ?? '—'} />
        </dl>
      )}
      {evidencias.length > 0 && (
        <div className="mt-5 border-t border-linha pt-4">
          <h3 className="font-sans text-sm font-semibold text-tinta">Evidências</h3>
          <ul className="mt-2 space-y-2">
            {evidencias.map((e, i) => (
              <EvidenciaItem key={i} e={e} />
            ))}
          </ul>
        </div>
      )}
      {j?.atencao && (
        <p className="mt-4 rounded-lg bg-g3-50 px-3.5 py-2 text-[13px] font-medium text-g3">
          Atenção: {rotuloMarcacao(j.atencao)}
        </p>
      )}
    </Cartao>
  )
}

export function EvidenciaItem({ e }: { e: Evidencia }) {
  return (
    <li className="rounded-lg border border-linha px-3.5 py-2.5 text-sm">
      <p className="text-xs text-tinta-soft">
        {e.data ? formatarData(e.data) : 'sem data'} · {e.origem}
        {e.somente_texto && <span className="font-semibold text-g3"> · só no texto</span>}
      </p>
      <p className="mt-0.5">{e.trecho}</p>
    </li>
  )
}

/* Sinalizações ------------------------------------------------------ */

function Sinalizacoes({ d }: { d: Detalhe }) {
  const marcacoes = d.fila_oficial?.marcacoes ?? d.estado_motor?.marcacoes ?? []
  const pendencias = d.estado_motor?.pendencias ?? []
  if (!marcacoes.length && !pendencias.length) return null
  return (
    <Cartao className="p-6">
      <h2 className="text-[1.75rem]">Sinalizações</h2>
      <ul className="mt-4 space-y-3">
        {marcacoes.map((m) => (
          <li key={m.marcacao}>
            <SeloSeveridade s={m.severidade} />
            <p className="mt-0.5 text-sm font-semibold">{rotuloMarcacao(m.marcacao)}</p>
          </li>
        ))}
        {pendencias.map((p) => (
          <li key={p} className="flex items-center gap-2.5">
            <PhoneCall size={15} className="shrink-0 text-g6" />
            <p className="text-sm font-semibold">{ROTULO_PENDENCIA[p] ?? p}</p>
          </li>
        ))}
      </ul>
    </Cartao>
  )
}

/* Linha do tempo ---------------------------------------------------- */

const ICONES: Record<string, typeof Activity> = {
  biopsia: Microscope,
  hba1c: FlaskConical,
  pronto_socorro: Activity,
  internacao: BedDouble,
  exame_imagem: ScanLine,
  consulta_reavaliacao: Stethoscope,
  contato_telefonico: Phone,
  falta: CalendarX,
}

function LinhaDoTempo({ eventos }: { eventos: EventoApi[] }) {
  return (
    <Cartao className="p-6">
      <h2 className="text-[1.75rem]">Linha do tempo clínica</h2>
      {eventos.length === 0 ? (
        <p className="mt-4 text-sm text-tinta-soft">Nenhum evento registrado.</p>
      ) : (
        <ol className="mt-5">
          {[...eventos].reverse().map((e, i, todos) => {
            const Icone = ICONES[e.tipo_evento] ?? Activity
            const piora = eventoDePiora(e.tipo_evento, e.resultado)
            return (
              <li key={e.id} className="relative flex gap-4 pb-5 last:pb-0">
                {i < todos.length - 1 && (
                  <span className="absolute left-[15px] top-8 h-[calc(100%-2rem)] w-px bg-linha" aria-hidden="true" />
                )}
                <span
                  className={cx(
                    'grid size-8 shrink-0 place-items-center rounded-full',
                    piora ? 'bg-urgente-50 text-urgente' : 'bg-nevoa-50 text-petroleo',
                  )}
                >
                  <Icone size={15} />
                </span>
                <div className="pt-1">
                  <p className="tabular text-xs font-semibold text-tinta-soft">
                    {formatarData(e.data_evento)} · {ROTULO_EVENTO[e.tipo_evento] ?? e.tipo_evento}:{' '}
                    <span className={piora ? 'text-urgente' : undefined}>{rotuloResultado(e.resultado)}</span>
                    {!e.processado_em && <span className="ml-2 text-g3">aguardando processamento</span>}
                  </p>
                  <p className="mt-0.5 text-sm">{e.descricao}</p>
                  <p className="text-xs text-tinta-soft">{e.origem}</p>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </Cartao>
  )
}

/* Histórico de decisões --------------------------------------------- */

const STATUS: Record<string, string> = {
  aprovada: 'Aprovada',
  rejeitada: 'Rejeitada',
  substituida: 'Substituída por outro pedido',
  obsoleta: 'Obsoleta',
}

function Historico({ d }: { d: Detalhe }) {
  const decididas = d.mudancas.filter((m) => m.status !== 'pendente')
  return (
    <Cartao className="p-6">
      <h2 className="text-[1.75rem]">Histórico de decisões</h2>
      {decididas.length === 0 ? (
        <p className="mt-4 text-sm text-tinta-soft">Nenhuma decisão registrada.</p>
      ) : (
        <ul className="mt-4 divide-y divide-linha">
          {[...decididas].reverse().map((m) => {
            const h = d.historico.find((x) => x.mudanca_id === m.id)
            return (
              <li key={m.id} className="py-4 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="tabular text-sm font-semibold">
                    {m.fila_atual} → {m.fila_proposta ?? 'saída'}
                  </span>
                  <span className="text-xs text-tinta-soft">{STATUS[m.status] ?? m.status}</span>
                  {h?.de_posicao && h.para_posicao && (
                    <span className="tabular text-xs text-tinta-soft">
                      · posição {h.de_posicao} → {h.para_posicao}
                    </span>
                  )}
                </div>
                {m.motivo_decisao && <p className="mt-1 text-sm">{m.motivo_decisao}</p>}
                {m.decidida_em && (
                  <p className="mt-1 text-xs text-tinta-soft">
                    {m.medico_nome} · {formatarInstante(m.decidida_em)}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Cartao>
  )
}
