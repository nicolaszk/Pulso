// Textos de exibição para os códigos que vêm do motor.

/** C509 → C50.9 */
export function formatarCid(cid: string) {
  return cid.length > 3 ? `${cid.slice(0, 3)}.${cid.slice(3)}` : cid
}

export const ROTULO_PENDENCIA: Record<string, string> = {
  sem_contato: 'Sem contato',
  nao_atendeu_2x: 'Não atendeu 2×',
  faltas_2x: 'Faltas 2×',
  hba1c_alta: 'HbA1c alta',
  duplicata_fundida: 'Duplicata fundida',
  irma_com_evento: 'Outra solicitação com evento',
  confirmar_saida: 'Confirmar saída',
}

export const ROTULO_EVENTO: Record<string, string> = {
  biopsia: 'Biópsia',
  hba1c: 'HbA1c',
  pronto_socorro: 'Pronto-socorro',
  internacao: 'Internação',
  exame_imagem: 'Exame de imagem',
  consulta_reavaliacao: 'Reavaliação',
  contato_telefonico: 'Contato telefônico',
  falta: 'Falta',
}

const RESULTADO: Record<string, string> = {
  positivo: 'positivo',
  negativo: 'negativo',
  inconclusivo: 'inconclusivo',
  atendido_liberado: 'atendido e liberado',
  observacao: 'em observação',
  alta: 'alta',
  estavel: 'estável',
  progressao: 'progressão',
  piora: 'piora',
  melhora: 'melhora',
  atendeu: 'atendeu',
  nao_atendeu: 'não atendeu',
  relata_piora: 'relata piora',
  relata_melhora: 'relata melhora',
  informou_cirurgia_outro_servico: 'operou em outro serviço',
  desistiu: 'desistiu',
  consulta: 'consulta',
  exame: 'exame',
  avaliacao_pre_anestesica: 'avaliação pré-anestésica',
}

export function rotuloResultado(r: string) {
  return RESULTADO[r] ?? r.replace(/_/g, ' ')
}

/** Eventos que o motor trata como piora. */
export function eventoDePiora(tipo: string, resultado: string) {
  return (
    tipo === 'pronto_socorro' ||
    tipo === 'internacao' ||
    (tipo === 'biopsia' && resultado === 'positivo') ||
    resultado === 'progressao' ||
    resultado === 'piora' ||
    resultado === 'relata_piora'
  )
}

export const ROTULO_MUDANCA = { subir: 'Aumentar prioridade', descer: 'Reduzir prioridade', sair: 'Sair da fila' } as const

/** "subir de G7 (Eletivo estavel) para G4 (...): motivo" → "motivo" */
export function motivoSemPrefixo(motivo: string) {
  const i = motivo.indexOf(': ')
  return i > 0 && /^(subir|descer|sair)/.test(motivo) ? motivo.slice(i + 2) : motivo
}

/** Justificativa do motor: "G1a Nome | motivo | entrada ..., data limite ... | ATENCAO: x" */
export function partesJustificativa(j: string) {
  const partes = j.split(' | ').slice(1)
  return {
    motivos: partes.filter((p) => !p.startsWith('entrada ') && !p.startsWith('ATENCAO')),
    prazo: partes.find((p) => p.startsWith('entrada ')),
    atencao: partes.find((p) => p.startsWith('ATENCAO'))?.replace('ATENCAO: ', ''),
  }
}
