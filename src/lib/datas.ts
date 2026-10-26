/** Data de referência da fila. Todos os cálculos de espera partem daqui. */
export const HOJE = '2026-10-23'

const DIA = 86_400_000

function parse(iso: string) {
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number)
  return Date.UTC(a, m - 1, d)
}

export function diasEntre(inicio: string, fim: string = HOJE) {
  return Math.round((parse(fim) - parse(inicio)) / DIA)
}

export function somarDias(iso: string, dias: number) {
  return new Date(parse(iso) + dias * DIA).toISOString().slice(0, 10)
}

export function formatarData(iso: string) {
  const [a, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${a}`
}

export function formatarDataHora(iso: string) {
  const hora = iso.length > 10 ? iso.slice(11, 16) : ''
  return hora ? `${formatarData(iso)} às ${hora}` : formatarData(iso)
}

/** Momento atual ancorado na data de referência, com o horário real do relógio. */
export function agora() {
  const d = new Date()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${HOJE}T${hh}:${mm}`
}

export function idadeEm(nascimento: string, ref: string = HOJE) {
  const [a, m, d] = nascimento.split('-').map(Number)
  const [ra, rm, rd] = ref.split('-').map(Number)
  return ra - a - (rm < m || (rm === m && rd < d) ? 1 : 0)
}

/** Timestamp com fuso (vindo da API) no horário local: dd/mm/aaaa às hh:mm. */
export function formatarInstante(iso: string) {
  const d = new Date(iso)
  const dd = (n: number) => String(n).padStart(2, '0')
  return `${dd(d.getDate())}/${dd(d.getMonth() + 1)}/${d.getFullYear()} às ${dd(d.getHours())}:${dd(d.getMinutes())}`
}
