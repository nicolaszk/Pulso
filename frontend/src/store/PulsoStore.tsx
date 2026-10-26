import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { filaInicial, REGULADOR_ATUAL } from '../data/pacientes'
import { MARCACOES, rotuloMarcacao } from '../data/revisao'
import type { FilaCodigo, Marcacao, Paciente, SinalIA } from '../data/types'
import { agora } from '../lib/datas'
import { ordenarFila, type LinhaFila } from '../lib/prioridade'

/**
 * As decisões dos reguladores ficam registradas como uma lista de ações.
 * O estado da fila é sempre a base + essas ações reaplicadas em ordem,
 * o que mantém a área pública e a profissional lendo a mesma fonte.
 */
type Acao =
  | { tipo: 'ajuste'; pacienteId: string; para: FilaCodigo; justificativa: string; data: string; profissional: string }
  | { tipo: 'marcacao'; marcacaoId: string; decisao: 'confirmar' | 'manter'; justificativa: string; data: string; profissional: string }
  | { tipo: 'sinal'; pacienteId: string; sinalId: string; status: SinalIA['status'] }

const CHAVE = 'pulso:decisoes:v2'
const base = filaInicial()

function lerAcoes(): Acao[] {
  try {
    const bruto = localStorage.getItem(CHAVE)
    return bruto ? (JSON.parse(bruto) as Acao[]) : []
  } catch {
    return []
  }
}

function aplicar(acoes: Acao[]) {
  const pacientes = new Map(base.map((p) => [p.id, p]))
  const marcacoes = new Map(MARCACOES.map((m) => [m.id, m]))
  const editar = (id: string, fn: (p: Paciente) => Paciente) => {
    const p = pacientes.get(id)
    if (p) pacientes.set(id, fn(p))
  }

  for (const a of acoes) {
    if (a.tipo === 'ajuste') {
      editar(a.pacienteId, (p) => ({
        ...p,
        fila: a.para,
        decisoes: [
          ...p.decisoes,
          {
            data: a.data,
            profissional: a.profissional,
            de: p.fila,
            para: a.para,
            justificativa: a.justificativa,
            tipo: 'ajuste',
            motivoPublico: 'reavaliação da equipe de regulação',
          },
        ],
      }))
    } else if (a.tipo === 'marcacao') {
      const m = marcacoes.get(a.marcacaoId)
      if (!m || m.status !== 'pendente') continue
      const confirmar = a.decisao === 'confirmar'
      marcacoes.set(m.id, { ...m, status: confirmar ? 'confirmada' : 'mantida' })
      editar(m.sid, (p) => {
        const para = confirmar && m.proposta ? m.proposta.para : p.fila
        return {
          ...p,
          fila: para,
          decisoes: [
            ...p.decisoes,
            {
              data: a.data,
              profissional: a.profissional,
              de: p.fila,
              para,
              justificativa: m.proposta ? a.justificativa : `${rotuloMarcacao(m.marcacao)}: ${a.justificativa}`,
              tipo: confirmar ? 'revisao-confirmada' : 'revisao-mantida',
              motivoPublico: confirmar ? m.proposta?.motivoPublico : undefined,
            },
          ],
        }
      })
    } else {
      editar(a.pacienteId, (p) => ({
        ...p,
        sinais: p.sinais.map((s) => (s.id === a.sinalId ? { ...s, status: a.status } : s)),
      }))
    }
  }
  return { pacientes: [...pacientes.values()], marcacoes: [...marcacoes.values()] }
}

interface Pulso {
  fila: LinhaFila[]
  linha: (id: string) => LinhaFila | undefined
  marcacoes: Marcacao[]
  pendentes: Marcacao[]
  ajustarFila: (pacienteId: string, para: FilaCodigo, justificativa: string) => void
  decidirMarcacao: (marcacaoId: string, decisao: 'confirmar' | 'manter', justificativa: string) => void
  marcarSinal: (pacienteId: string, sinalId: string, status: SinalIA['status']) => void
}

const Contexto = createContext<Pulso | null>(null)

export function PulsoProvider({ children }: { children: ReactNode }) {
  const [acoes, setAcoes] = useState<Acao[]>(lerAcoes)

  useEffect(() => {
    try {
      localStorage.setItem(CHAVE, JSON.stringify(acoes))
    } catch {
      /* armazenamento indisponível: segue só em memória */
    }
  }, [acoes])

  // Mantém abas abertas (pública e profissional) sincronizadas.
  useEffect(() => {
    const ouvir = (e: StorageEvent) => e.key === CHAVE && setAcoes(lerAcoes())
    window.addEventListener('storage', ouvir)
    return () => window.removeEventListener('storage', ouvir)
  }, [])

  const estado = useMemo(() => {
    const { pacientes, marcacoes } = aplicar(acoes)
    const fila = ordenarFila(pacientes)
    const indice = new Map(fila.map((l) => [l.paciente.id, l]))
    return { fila, indice, marcacoes }
  }, [acoes])

  const registrar = useCallback((a: Acao) => setAcoes((atual) => [...atual, a]), [])

  const valor = useMemo<Pulso>(
    () => ({
      fila: estado.fila,
      linha: (id) => estado.indice.get(id),
      marcacoes: estado.marcacoes,
      pendentes: estado.marcacoes.filter((m) => m.status === 'pendente'),
      ajustarFila: (pacienteId, para, justificativa) =>
        registrar({ tipo: 'ajuste', pacienteId, para, justificativa, data: agora(), profissional: REGULADOR_ATUAL }),
      decidirMarcacao: (marcacaoId, decisao, justificativa) =>
        registrar({ tipo: 'marcacao', marcacaoId, decisao, justificativa, data: agora(), profissional: REGULADOR_ATUAL }),
      marcarSinal: (pacienteId, sinalId, status) => registrar({ tipo: 'sinal', pacienteId, sinalId, status }),
    }),
    [estado, registrar],
  )

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}

export function usePulso() {
  const ctx = useContext(Contexto)
  if (!ctx) throw new Error('usePulso precisa estar dentro de <PulsoProvider>')
  return ctx
}
