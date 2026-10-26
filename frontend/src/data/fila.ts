// Classificação da fila em 7 níveis (G1 dividido em a/b).
// A ordem dos níveis é a ordem de atendimento; dentro de cada nível, a pontuação desempata.

export type FilaCodigo = 'G1a' | 'G1b' | 'G2' | 'G3' | 'G4' | 'G5' | 'G6' | 'G7'
export type Severidade = 'alta' | 'media' | 'baixa' | 'informativa'

export const ORDEM_FILAS: FilaCodigo[] = ['G1a', 'G1b', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7']

export const NOME_FILA: Record<FilaCodigo, string> = {
  G1a: 'Oncológico em progressão',
  G1b: 'Agudo não oncológico',
  G2: 'Oncológico confirmado',
  G3: 'Suspeita oncológica',
  G4: 'Deterioração recente',
  G5: 'Alta carga de sintomas',
  G6: 'Sintomático moderado',
  G7: 'Eletivo estável',
}

/** Prazo de referência, em dias, para cada nível. */
export const PRAZO_FILA: Record<FilaCodigo, number> = {
  G1a: 15,
  G1b: 15,
  G2: 21,
  G3: 60,
  G4: 60,
  G5: 60,
  G6: 180,
  G7: 360,
}

/** Tamanho de cada nível na carga de 23/10/2026. */
export const TAMANHO_FILA: Record<FilaCodigo, number> = {
  G1a: 53,
  G1b: 70,
  G2: 142,
  G3: 16,
  G4: 118,
  G5: 95,
  G6: 194,
  G7: 209,
}

/** Nível exibido ao paciente, sem rótulo clínico. */
export const NIVEL_PUBLICO: Record<FilaCodigo, { nivel: number; texto: string }> = {
  G1a: { nivel: 1, texto: 'Sua cirurgia tem a maior prioridade da fila.' },
  G1b: { nivel: 1, texto: 'Sua cirurgia tem a maior prioridade da fila.' },
  G2: { nivel: 2, texto: 'Sua cirurgia tem prioridade muito alta.' },
  G3: { nivel: 3, texto: 'Sua cirurgia tem prioridade alta e está em investigação.' },
  G4: { nivel: 4, texto: 'Sua cirurgia tem prioridade alta por piora recente.' },
  G5: { nivel: 5, texto: 'Sua cirurgia tem prioridade acima dos casos eletivos.' },
  G6: { nivel: 6, texto: 'Sua cirurgia é necessária, sem sinais de urgência no momento.' },
  G7: { nivel: 7, texto: 'Sua cirurgia pode ser programada sem prejuízo à sua saúde.' },
}

export function ehOncologico(cid: string) {
  return cid.toUpperCase().startsWith('C')
}

/** Regra de ouro: neoplasia maligna nunca desce para níveis sem urgência (G4 em diante). */
export function filaPermitida(f: FilaCodigo, cid: string) {
  return !ehOncologico(cid) || ORDEM_FILAS.indexOf(f) <= ORDEM_FILAS.indexOf('G3')
}

export function iniciais(nome: string) {
  const partes = nome.trim().split(/\s+/)
  return ((partes[0]?.[0] ?? '') + (partes.length > 1 ? partes[partes.length - 1][0] : '')).toUpperCase()
}
