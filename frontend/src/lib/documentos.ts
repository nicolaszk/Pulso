export function soDigitos(v: string) {
  return v.replace(/\D/g, '')
}

function digitoCpf(base: string) {
  const peso = base.length + 1
  const soma = [...base].reduce((acc, n, i) => acc + Number(n) * (peso - i), 0)
  const resto = (soma * 10) % 11
  return resto === 10 ? 0 : resto
}

export function cpfValido(valor: string) {
  const d = soDigitos(valor)
  if (d.length !== 11 || /^(\d)\1+$/.test(d)) return false
  const d1 = digitoCpf(d.slice(0, 9))
  const d2 = digitoCpf(d.slice(0, 9) + d1)
  return d.endsWith(`${d1}${d2}`)
}

/** Completa os dois dígitos verificadores de uma base de 9 dígitos. */
export function montarCpf(base9: string) {
  const d1 = digitoCpf(base9)
  return base9 + d1 + digitoCpf(base9 + d1)
}

export function cnsValido(valor: string) {
  const d = soDigitos(valor)
  return d.length === 15 && /^[1-9]/.test(d)
}

/** Máscara progressiva: CPF até 11 dígitos, Cartão Nacional de Saúde até 15. */
export function mascararDocumento(valor: string) {
  const d = soDigitos(valor).slice(0, 15)
  if (d.length <= 11) {
    return d
      .replace(/^(\d{3})(\d)/, '$1.$2')
      .replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
      .replace(/\.(\d{3})(\d{1,2})$/, '.$1-$2')
  }
  return d.replace(/^(\d{3})(\d{4})(\d{4})(\d{0,4})$/, '$1 $2 $3 $4').trim()
}

export function mascararData(valor: string) {
  const d = soDigitos(valor).slice(0, 8)
  return d.replace(/^(\d{2})(\d)/, '$1/$2').replace(/^(\d{2})\/(\d{2})(\d)/, '$1/$2/$3')
}

/** dd/mm/aaaa → aaaa-mm-dd, ou null se a data não existir. */
export function dataBrParaIso(valor: string) {
  const m = valor.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  if (!m) return null
  const [, d, mes, a] = m
  const iso = `${a}-${mes}-${d}`
  const t = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(t.getTime()) || t.toISOString().slice(0, 10) !== iso) return null
  return iso
}
