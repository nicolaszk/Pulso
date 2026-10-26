import { createContext, useContext, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, ErroApi } from '../api/cliente'

interface Sessao {
  medicoId: number
  nome: string
  crm: string
  funcao: string
}

interface Auth {
  sessao: Sessao | null
  entrar: (crm: string, senha: string) => Promise<void>
  sair: () => void
}

const CHAVE = 'pulso:sessao:v2'
const Contexto = createContext<Auth | null>(null)

function lerSessao(): Sessao | null {
  try {
    const bruto = sessionStorage.getItem(CHAVE)
    return bruto ? (JSON.parse(bruto) as Sessao) : null
  } catch {
    return null
  }
}

const digitos = (v: string) => v.replace(/\D/g, '')

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sessao, setSessao] = useState<Sessao | null>(lerSessao)

  // O backend ainda não tem autenticação: o médico é identificado pelo CRM cadastrado.
  async function entrar(crm: string, senha: string) {
    if (!digitos(crm) || senha.length < 4) throw new ErroApi(401, 'Identificação ou senha incorretas.')
    const medico = (await api.medicos()).find((m) => digitos(m.crm) === digitos(crm))
    if (!medico) throw new ErroApi(401, 'Identificação ou senha incorretas.')
    const s = { medicoId: medico.id, nome: medico.nome, crm: medico.crm, funcao: 'Regulação' }
    try {
      sessionStorage.setItem(CHAVE, JSON.stringify(s))
    } catch {
      /* sessão só em memória */
    }
    setSessao(s)
  }

  const sair = () => {
    try {
      sessionStorage.removeItem(CHAVE)
    } catch {
      /* nada a limpar */
    }
    setSessao(null)
  }

  return <Contexto.Provider value={{ sessao, entrar, sair }}>{children}</Contexto.Provider>
}

export function useAuth() {
  const ctx = useContext(Contexto)
  if (!ctx) throw new Error('useAuth precisa estar dentro de <AuthProvider>')
  return ctx
}

export function RotaProtegida({ children }: { children: ReactNode }) {
  const { sessao } = useAuth()
  const local = useLocation()
  if (!sessao) return <Navigate to="/profissional/entrar" replace state={{ de: local.pathname }} />
  return <>{children}</>
}
