import { useCallback, useEffect, useRef, useState } from 'react'

interface Estado<T> {
  dados: T | null
  erro: string | null
  carregando: boolean
}

/** Busca dados da API e expõe carregamento, erro e uma forma de recarregar. */
export function useApi<T>(buscar: () => Promise<T>, deps: unknown[] = []) {
  const [estado, setEstado] = useState<Estado<T>>({ dados: null, erro: null, carregando: true })
  const ultima = useRef(0)

  const carregar = useCallback(() => {
    const id = ++ultima.current
    setEstado((e) => ({ ...e, carregando: true, erro: null }))
    buscar()
      .then((dados) => id === ultima.current && setEstado({ dados, erro: null, carregando: false }))
      .catch((e: Error) => id === ultima.current && setEstado((s) => ({ ...s, erro: e.message, carregando: false })))
  }, deps)

  useEffect(carregar, [carregar])

  return { ...estado, recarregar: carregar }
}
