import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, LockKeyhole } from 'lucide-react'
import { Botao, Campo, Marca } from '../../components/ui'
import { useAuth } from '../../store/auth'

export function Entrar() {
  const { sessao, entrar } = useAuth()
  const navegar = useNavigate()
  const local = useLocation()
  const [identificacao, setIdentificacao] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  if (sessao) return <Navigate to="/profissional/visao" replace />

  async function enviar(e: FormEvent) {
    e.preventDefault()
    if (!identificacao.trim() || !senha) {
      setErro('Preencha a identificação profissional e a senha.')
      return
    }
    setErro(null)
    setEnviando(true)
    try {
      await entrar(identificacao, senha)
      const destino = (local.state as { de?: string } | null)?.de ?? '/profissional/visao'
      navegar(destino, { replace: true })
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Identificação ou senha incorretas.')
      setEnviando(false)
    }
  }

  return (
    <div className="grid min-h-dvh md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <aside className="flex flex-col justify-between bg-petroleo px-6 py-8 text-white sm:px-10 md:py-12">
        <Marca claro />
        <div className="my-10 md:my-0">
          <h1 className="max-w-sm text-[2.5rem] text-white sm:text-5xl">Regulação com responsabilidade.</h1>
          <p className="mt-4 max-w-sm text-[15px] text-white/80">
            Fila priorizada, revisões propostas a partir de eventos clínicos e o histórico de cada decisão.
          </p>
        </div>
        <p className="hidden text-[13px] text-white/60 md:block">Acesso registrado conforme a LGPD.</p>
      </aside>

      <main className="flex items-start justify-center bg-areia px-4 py-10 sm:px-10 md:items-center">
        <div className="w-full max-w-md">
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-petroleo hover:underline">
            <ArrowLeft size={15} /> Voltar ao início
          </Link>
          <form onSubmit={enviar} noValidate className="mt-6 rounded-xl border border-linha bg-white p-6 sm:p-8">
            <span className="grid size-10 place-items-center rounded-full bg-nevoa-50 text-petroleo">
              <LockKeyhole size={18} />
            </span>
            <h2 className="mt-4 text-[2rem]">Entrada profissional</h2>
            <p className="mt-1 text-sm text-tinta-soft">Exclusivo para médicos reguladores autorizados.</p>

            {erro && (
              <p role="alert" className="mt-5 rounded-lg bg-urgente-50 px-3.5 py-2.5 text-sm font-medium text-urgente">
                {erro}
              </p>
            )}

            <div className="mt-6 space-y-5">
              <Campo
                rotulo="Identificação profissional"
                dica="CRM cadastrado na regulação."
                autoComplete="username"
                value={identificacao}
                onChange={(e) => setIdentificacao(e.target.value)}
                disabled={enviando}
              />
              <Campo
                rotulo="Senha"
                type="password"
                autoComplete="current-password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                disabled={enviando}
              />
            </div>
            <Botao type="submit" className="mt-7 w-full" carregando={enviando}>
              Entrar
            </Botao>
          </form>
          <p className="mt-4 text-center text-[13px] text-tinta-soft md:hidden">Acesso registrado conforme a LGPD.</p>
        </div>
      </main>
    </div>
  )
}
