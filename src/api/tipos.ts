// Formato das respostas da API do Pulso (Pulso-Backend/backend/src/main.py).
import type { FilaCodigo, Severidade } from '../data/fila'

export interface ItemFila {
  posicao: number
  solicitacao_id: string
  fila: FilaCodigo
  posicao_fila: number
  data_limite_efetiva: string
  posicao_inicial: number
  justificativa: string
  cid_principal: string
  oncologico: boolean
  mudanca_pendente: number | null
  mudanca_tipo: TipoMudanca | null
  fila_proposta: FilaCodigo | null
  paciente_id: string
  paciente_nome: string
  idade: number
  municipio: string
  procedimento: string
  especialidade: string
  data_entrada_fila: string
  dias_em_fila: number
  prioridade_regulacao: 'alta' | 'media' | 'baixa' | null
}

export type TipoMudanca = 'subir' | 'descer' | 'sair'
export type StatusMudanca = 'pendente' | 'aprovada' | 'rejeitada' | 'substituida' | 'obsoleta'

export interface Evidencia {
  data?: string | null
  tipo?: string
  origem?: string
  trecho?: string
  evento_id?: string | null
  somente_texto?: boolean
}

export interface Mudanca {
  id: number
  solicitacao_id: string
  tipo: TipoMudanca
  status: StatusMudanca
  fila_atual: FilaCodigo
  fila_proposta: FilaCodigo | null
  posicao_atual: number | null
  /** estimativa se só este pedido for aprovado (vários pedidos podem cair na mesma) */
  posicao_proposta: number | null
  /** posição na fila recomendada de agora, com todos os pedidos aprovados (só pendentes) */
  posicao_recomendada: number | null
  motivo: string
  evidencias: Evidencia[]
  evento_id: string | null
  oncologico: boolean
  criada_em: string
  /** muda quando um evento novo atualiza o pedido (e, com ele, os fatos da explicação) */
  atualizada_em: string
  medico_id: number | null
  medico_nome: string | null
  decidida_em: string | null
  motivo_decisao: string | null
  paciente_nome: string
  procedimento: string
  /** Texto em linguagem clara gerado pelo backend (LLM), quando já existe */
  explicacao?: string | null
}

/** GET /solicitacoes/{id}/explicacao e /mudancas/{id}/explicacao */
export interface Explicacao {
  alvo: 'solicitacao' | 'mudanca'
  alvo_id: string
  texto: string
  fonte: 'llm' | 'template'
  em_cache: boolean
}

/** POST /eventos/processar: o que os eventos lidos causaram na caixa do médico */
export interface ResultadoProcessamento {
  eventos: number
  /** pedidos novos abertos */
  aberta: number
  atualizada: number
  obsoleta: number
  sem_mudanca: number
  /** eventos que ainda faltam processar */
  pendentes: number
}

export interface ResultadoDecisao {
  mudanca_id: number
  status: 'aprovada' | 'rejeitada'
  solicitacao_id?: string
  de?: { fila: FilaCodigo; posicao_final: number }
  para?: { fila: FilaCodigo; posicao_final: number } | null
}

export interface MarcacaoMotor {
  marcacao: string
  severidade: Severidade
}

export interface EventoApi {
  id: string
  data_evento: string
  tipo_evento: string
  resultado: string
  valor_numerico: number | null
  descricao: string
  origem: string
  processado_em: string | null
}

export interface Detalhe {
  id: string
  paciente_id: string
  procedimento: string
  especialidade: string
  cid_principal: string
  cid_descricao: string
  intensidade_dor_eva: number | null
  limitacao_funcional: string | null
  justificativa_clinica: string
  observacoes: string | null
  data_entrada_fila: string
  prioridade_regulacao: 'alta' | 'media' | 'baixa' | null
  status: 'ativa' | 'duplicata' | 'saiu'
  motivo_status: string | null
  paciente: {
    id: string
    nome: string
    sexo: 'F' | 'M'
    idade: number
    municipio: string
    distancia_hospital_km: number | null
    comorbidades: string[]
  }
  fila_oficial: {
    posicao: number
    posicao_inicial: number
    fila: FilaCodigo
    posicao_fila: number
    data_limite_efetiva: string
    justificativa: string
    marcacoes: MarcacaoMotor[]
  } | null
  estado_motor: {
    fila: FilaCodigo
    data_limite_efetiva: string
    n_sinais: number
    dor: number | null
    motivos: string[]
    sinais: string[]
    evidencias: Record<string, Evidencia[]>
    marcacoes: MarcacaoMotor[]
    pendencias: string[]
  } | null
  eventos: EventoApi[]
  mudancas: Omit<Mudanca, 'paciente_nome' | 'procedimento' | 'solicitacao_id' | 'oncologico' | 'posicao_atual' | 'posicao_proposta' | 'posicao_recomendada' | 'atualizada_em'>[]
  historico: {
    mudanca_id: number
    acao: 'mudanca' | 'saida'
    de_fila: FilaCodigo | null
    para_fila: FilaCodigo | null
    de_posicao: number | null
    para_posicao: number | null
    registrado_em: string
    medico_nome: string
  }[]
}

export interface Resumo {
  solicitacoes: Record<string, number>
  eventos: { processados: number; pendentes: number; quarentena: number }
  filas: { codigo: FilaCodigo; nome: string; oficial: number; recomendada: number }[]
  mudancas: Record<string, number>
  prazo_estourado: number
  pendencias: number
}

export interface MarcacaoApi {
  solicitacao_id: string
  paciente_nome: string
  fila: FilaCodigo
  posicao: number
  marcacao: string
  severidade: Severidade
}

export interface Medico {
  id: number
  nome: string
  crm: string
  especialidade: string
}
