import { ehOncologico, ORDEM_FILAS, PRAZO_FILA } from '../data/fila'
import type { Paciente } from '../data/types'
import { diasEntre, HOJE } from './datas'

export interface Fatores {
  gravidade: number
  piora: number
  eventosPiora: number
  tempo: number
  percentualPrazo: number
  risco: number
  total: number
}

export const LIMITES = { gravidade: 40, piora: 25, tempo: 20, risco: 15 }

export function calcularFatores(p: Paciente): Fatores {
  const dias = diasEntre(p.dataEntrada)
  const percentualPrazo = dias / PRAZO_FILA[p.fila]
  const eventosPiora = p.eventos.filter((e) => {
    const d = diasEntre(e.data, HOJE)
    return e.piora && d >= 0 && d <= 30
  }).length
  const piora = Math.min(LIMITES.piora, eventosPiora * 11)
  const tempo = Math.min(LIMITES.tempo, Math.round(percentualPrazo * LIMITES.tempo))
  const total = p.gravidade + piora + tempo + p.risco
  return { gravidade: p.gravidade, piora, eventosPiora, tempo, percentualPrazo, risco: p.risco, total }
}

export interface LinhaFila {
  paciente: Paciente
  posicao: number
  posicaoChegada: number
  dias: number
  fatores: Fatores
  resumo: string
}

export function resumoMotivo(p: Paciente, f: Fatores, dias: number) {
  const espera = `${dias} dias (prazo ${PRAZO_FILA[p.fila]})`
  if (ehOncologico(p.cid)) return `Neoplasia maligna ${p.cid}; ${espera}.`
  const motivo =
    p.motivo ??
    (f.eventosPiora > 0 ? `${f.eventosPiora} ${f.eventosPiora > 1 ? 'eventos' : 'evento'} de piora em 30 dias` : p.cidDescricao)
  return `${motivo}; ${espera}.`
}

/** Nível primeiro (garante a regra de ouro), depois pontuação e tempo de espera. */
export function ordenarFila(pacientes: Paciente[]): LinhaFila[] {
  const chegada = [...pacientes]
    .sort((a, b) => a.dataEntrada.localeCompare(b.dataEntrada) || a.id.localeCompare(b.id))
    .reduce<Record<string, number>>((acc, p, i) => ((acc[p.id] = i + 1), acc), {})

  return pacientes
    .map((paciente) => ({ paciente, fatores: calcularFatores(paciente), dias: diasEntre(paciente.dataEntrada) }))
    .sort(
      (a, b) =>
        ORDEM_FILAS.indexOf(a.paciente.fila) - ORDEM_FILAS.indexOf(b.paciente.fila) ||
        b.fatores.total - a.fatores.total ||
        b.dias - a.dias,
    )
    .map((l, i) => ({
      ...l,
      posicao: i + 1,
      posicaoChegada: chegada[l.paciente.id],
      resumo: resumoMotivo(l.paciente, l.fatores, l.dias),
    }))
}

/** Verifica a regra de ouro: nenhum oncológico abaixo de um paciente sem urgência (G4 em diante). */
export function regraDeOuro(fila: LinhaFila[]) {
  const semUrgencia = ORDEM_FILAS.indexOf('G4')
  const ultimoOnco = Math.max(0, ...fila.filter((l) => ehOncologico(l.paciente.cid)).map((l) => l.posicao))
  const primeiroSemUrgencia = Math.min(
    Infinity,
    ...fila.filter((l) => ORDEM_FILAS.indexOf(l.paciente.fila) >= semUrgencia).map((l) => l.posicao),
  )
  return ultimoOnco < primeiroSemUrgencia
}
