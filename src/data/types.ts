import type { FilaCodigo, Severidade } from './fila'

export type { FilaCodigo, Severidade }

export type TipoEvento =
  | 'entrada'
  | 'pronto-socorro'
  | 'internacao'
  | 'exame'
  | 'biopsia'
  | 'contato'
  | 'consulta'
  | 'falta'

export interface EventoClinico {
  data: string // ISO yyyy-mm-dd
  tipo: TipoEvento
  descricao: string
  /** Conta como sinal de piora no cálculo da pontuação */
  piora?: boolean
}

export interface SinalIA {
  id: string
  /** Trecho exato da justificativa que é destacado */
  trecho: string
  rotulo: string
  status: 'sugerido' | 'confirmado' | 'descartado'
}

export interface Decisao {
  data: string // ISO com horário
  profissional: string
  de: FilaCodigo | null
  para: FilaCodigo
  justificativa: string
  tipo: 'inclusao' | 'ajuste' | 'revisao-confirmada' | 'revisao-mantida'
  /** Texto curto, em linguagem simples, que o paciente pode ver */
  motivoPublico?: string
}

export interface Paciente {
  /** Identificador da solicitação (SOL-aaaa-nnnnn) */
  id: string
  pacienteId: string
  nome: string
  idade: number
  sexo: 'F' | 'M'
  nascimento?: string
  cpf?: string
  cns?: string
  municipio: string
  procedimento: string
  especialidade: string
  cid: string
  cidDescricao: string
  fila: FilaCodigo
  /** Prioridade marcada à mão na inclusão (sistema antigo) */
  prioridadeManual: 'alta' | 'media' | 'baixa'
  dataEntrada: string
  /** Pontos de gravidade clínica (0–40) */
  gravidade: number
  /** Pontos de risco estimado (0–15) */
  risco: number
  /** Frase curta usada no resumo do motivo */
  motivo?: string
  eventos: EventoClinico[]
  justificativa: string
  observacao?: string
  sinais: SinalIA[]
  decisoes: Decisao[]
}

/** Marcação que pede decisão do regulador. Pode trazer uma proposta de mudança de nível. */
export interface Marcacao {
  id: string
  sid: string
  marcacao: string
  descricao: string
  severidade: Severidade
  evidencias?: string[]
  proposta?: { de: FilaCodigo; para: FilaCodigo; motivoPublico: string }
  data: string
  status: 'pendente' | 'confirmada' | 'mantida'
}

export interface Pendencia {
  sid: string
  tipo: string
  rotulo: string
  detalhe: string
}
