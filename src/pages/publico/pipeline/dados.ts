// Dados da página do pipeline. fila.json e recibos.json saem do pipeline real (scripts/dados_historia.py),
// rodado no dataset completo do desafio: 902 solicitações ativas, 1.489 eventos válidos.
import bruto from './dados/fila.json'
import { ORDEM_FILAS, type FilaCodigo } from '../../../data/fila'

/** Cores do tema (espelham o @theme de src/index.css) para o que é desenhado em canvas. */
export const COR = {
  petroleo: '#064f5f',
  petroleo900: '#043a46',
  oceano: '#1f727c',
  agua: '#6aa9ab',
  nevoa: '#cfdee3',
  nevoa50: '#e7eff1',
  areia: '#f1efeb',
  tinta: '#2a4347',
  tintaSoft: '#566d70',
  linha: '#dcd8d1',
  urgente: '#9a3324',
  sucesso: '#2c6b47',
}

/** Cor de cada nível, na mesma escala de TOM_FILA (G1a e G1b dividem o g1). */
export const COR_NIVEL: Record<FilaCodigo, { cor: string; fundo: string }> = {
  G1a: { cor: '#a32d2d', fundo: '#f7dedb' },
  G1b: { cor: '#a32d2d', fundo: '#f7dedb' },
  G2: { cor: '#bf4a1f', fundo: '#fae3d8' },
  G3: { cor: '#a8620b', fundo: '#f8ead4' },
  G4: { cor: '#87700a', fundo: '#f3edc8' },
  G5: { cor: '#4f7a26', fundo: '#e3eed6' },
  G6: { cor: '#1d6f8a', fundo: '#d9eaf1' },
  G7: { cor: '#55628c', fundo: '#e3e6f1' },
}
export const corNivel = (i: number) => COR_NIVEL[ORDEM_FILAS[i]].cor

export interface Ponto {
  /** nível só com o cadastro (índice em ORDEM_FILAS) */
  ini: number
  /** nível com todos os eventos; -1 = sai da fila */
  fim: number
  /** CID C* */
  onco: boolean
  /** posição na fila recomendada; 0 = sai */
  rec: number
}

/** Um ponto por solicitação ativa (902), na ordem oficial de hoje (só cadastro). */
export const PONTOS: Ponto[] = bruto.pontos.map(([ini, fim, fl, , rec]) => ({ ini, fim, onco: (fl & 1) > 0, rec }))

/** SOL-2026-00610, a "621": índice dela em PONTOS. */
export const HEROI = bruto.heroi

export const TIPOS_EVENTO = ['LIGAÇÃO', 'HbA1c', 'PS', 'FALTA', 'BIÓPSIA', 'IMAGEM', 'REAVALIAÇÃO', 'INTERNAÇÃO']

/** 0 = não pediu mudança de nível, 1 = abriu pedido, 2 = evidência nova num pedido aberto */
export type Acao = 0 | 1 | 2

export interface Evento {
  tipo: number
  acao: Acao
  /** o pedido novo substituiu um que ainda esperava o médico */
  substituiu: boolean
  /** índice do paciente em PONTOS (-1 = fora da fila ativa) */
  paciente: number
  /** nível que o motor recomenda depois do evento (-1 = sair da fila) */
  nivel: number
}

/** Os 1.489 eventos na ordem em que o motor processou (data, id). */
export const EVENTOS: Evento[] = bruto.eventos.map(([tipo, acao, subst, paciente, nivel]) => ({
  tipo,
  acao: acao as Acao,
  substituiu: subst === 1,
  paciente,
  nivel,
}))

/** Recibo de uma posição da fila recomendada: [posição, solicitação, nível, CID, procedimento, justificativa] */
export type Recibo = [number, string, string, string, string, string]
export const carregarRecibos = () => import('./dados/recibos.json').then((m) => m.default as unknown as Recibo[])

/** Regras de entrada de cada nível (motor de priorização, baseado no SWALIS). */
export const REGRA_FILA: Record<FilaCodigo, string> = {
  G1a: 'Neoplasia maligna (CID C* ou biópsia positiva) com progressão: imagem, reavaliação com piora, PS, internação ou alarme no texto',
  G1b: 'CID urgente (I20.0, K40.0, K40.3, K42.0, K43.0, K80.0, N13.2, I83.2) ou quadro agudo no texto',
  G2: 'Neoplasia maligna sem sinal de progressão',
  G3: 'CID incerto (D37–D48, D05, R91) ou suspeita no texto',
  G4: 'Piora por evento nos últimos 180 dias, piora relatada ou alarme no texto',
  G5: 'Dor 7 ou mais, ou limitação grave',
  G6: 'Dor 4 a 6, ou limitação moderada',
  G7: 'O restante',
}
