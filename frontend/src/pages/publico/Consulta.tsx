import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, SearchX, WifiOff } from 'lucide-react'
import { Botao, Campo, Cartao, TOM_FILA, cx } from '../../components/ui'
import { formatarData } from '../../lib/datas'
import { cnsValido, cpfValido, dataBrParaIso, mascararData, mascararDocumento, soDigitos } from '../../lib/documentos'
import { NIVEL_PUBLICO } from '../../data/fila'
import { consultarEncaminhamento, type EncaminhamentoPublico } from '../../store/consultaPublica'
import { usePulso } from '../../store/PulsoStore'

type Estado =
  | { fase: 'formulario' }
  | { fase: 'consultando' }
  | { fase: 'encontrado'; dados: EncaminhamentoPublico }
  | { fase: 'nao-encontrado' }
  | { fase: 'erro' }

interface Erros {
  documento?: string
  nascimento?: string
}

function validar(documento: string, nascimento: string): Erros {
  const erros: Erros = {}
  const d = soDigitos(documento)
  if (!d) erros.documento = 'Informe o CPF ou o número do Cartão Nacional de Saúde.'
  else if (d.length === 11 ? !cpfValido(d) : d.length === 15 ? !cnsValido(d) : true)
    erros.documento = 'Número inválido. O CPF tem 11 dígitos e o Cartão Nacional de Saúde, 15.'

  if (!nascimento) erros.nascimento = 'Informe sua data de nascimento.'
  else {
    const iso = dataBrParaIso(nascimento)
    if (!iso || iso > '2026-10-23' || iso < '1900-01-01') erros.nascimento = 'Use o formato dia/mês/ano, por exemplo 14/03/1974.'
  }
  return erros
}

export function Consulta() {
  const { fila } = usePulso()
  const [documento, setDocumento] = useState('')
  const [nascimento, setNascimento] = useState('')
  const [erros, setErros] = useState<Erros>({})
  const [estado, setEstado] = useState<Estado>({ fase: 'formulario' })
  const topo = useRef<HTMLDivElement>(null)

  async function consultar(e?: FormEvent) {
    e?.preventDefault()
    const v = validar(documento, nascimento)
    setErros(v)
    if (v.documento || v.nascimento) return
    setEstado({ fase: 'consultando' })
    try {
      const dados = await consultarEncaminhamento(fila, documento, dataBrParaIso(nascimento)!)
      setEstado(dados ? { fase: 'encontrado', dados } : { fase: 'nao-encontrado' })
    } catch {
      setEstado({ fase: 'erro' })
    }
    requestAnimationFrame(() => topo.current?.focus())
  }

  function novaConsulta() {
    setDocumento('')
    setNascimento('')
    setErros({})
    setEstado({ fase: 'formulario' })
  }

  if (estado.fase === 'encontrado') {
    return (
      <div ref={topo} tabIndex={-1} className="outline-none">
        <Resultado dados={estado.dados} aoVoltar={novaConsulta} />
      </div>
    )
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1fr_minmax(0,440px)] md:gap-16 md:py-20">
      <div className="max-w-md md:pt-6">
        <h1 className="text-[2.75rem] sm:text-6xl">Acompanhe sua cirurgia</h1>
        <p className="mt-5 text-[17px] text-tinta-soft">
          Veja a situação do seu encaminhamento, a prioridade definida pela equipe médica e há quanto tempo você
          aguarda.
        </p>
        <dl className="mt-9 divide-y divide-linha border-y border-linha text-sm">
          {[
            ['Você vai precisar', 'CPF ou Cartão Nacional de Saúde e data de nascimento.'],
            ['O que aparece', 'Somente as suas informações.'],
          ].map(([t, d]) => (
            <div key={t} className="grid grid-cols-[8.5rem_1fr] gap-3 py-3">
              <dt className="font-semibold text-petroleo">{t}</dt>
              <dd>{d}</dd>
            </div>
          ))}
        </dl>
        <Link
          to="/como-funciona"
          className="mt-6 inline-flex items-center gap-1.5 text-sm font-semibold text-petroleo underline-offset-4 hover:underline"
        >
          Como a fila é organizada <ArrowRight size={15} />
        </Link>
      </div>

      <div ref={topo} tabIndex={-1} className="outline-none">
        <Cartao className="p-6 shadow-[0_1px_2px_rgba(4,58,70,0.06)] sm:p-8">
          {estado.fase === 'nao-encontrado' ? (
            <Retorno
              icone={<SearchX size={22} />}
              titulo="Nenhum encaminhamento encontrado"
              texto="Confira o número do documento e a data de nascimento. Se os dados estiverem corretos, procure a unidade de saúde onde você foi encaminhado."
              acao="Corrigir dados"
              aoAgir={() => setEstado({ fase: 'formulario' })}
            />
          ) : estado.fase === 'erro' ? (
            <Retorno
              icone={<WifiOff size={22} />}
              titulo="Não foi possível consultar agora"
              texto="Houve uma falha de conexão. Seus dados não foram perdidos; tente novamente em alguns instantes."
              acao="Tentar novamente"
              aoAgir={() => consultar()}
            />
          ) : (
            <form onSubmit={consultar} noValidate aria-busy={estado.fase === 'consultando'}>
              <h2 className="text-[1.75rem]">Consultar</h2>
              <p className="mt-1 text-sm text-tinta-soft">Preencha os dois campos.</p>
              <div className="mt-6 space-y-5">
                <Campo
                  rotulo="CPF ou Cartão Nacional de Saúde"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="000.000.000-00"
                  value={documento}
                  onChange={(e) => {
                    setDocumento(mascararDocumento(e.target.value))
                    setErros((x) => ({ ...x, documento: undefined }))
                  }}
                  erro={erros.documento}
                  dica={!erros.documento && 'Somente números. O Cartão Nacional de Saúde tem 15 dígitos.'}
                  disabled={estado.fase === 'consultando'}
                />
                <Campo
                  rotulo="Data de nascimento"
                  inputMode="numeric"
                  autoComplete="bday"
                  placeholder="dd/mm/aaaa"
                  value={nascimento}
                  onChange={(e) => {
                    setNascimento(mascararData(e.target.value))
                    setErros((x) => ({ ...x, nascimento: undefined }))
                  }}
                  erro={erros.nascimento}
                  disabled={estado.fase === 'consultando'}
                />
              </div>
              <Botao type="submit" className="mt-7 w-full" carregando={estado.fase === 'consultando'}>
                {estado.fase === 'consultando' ? 'Consultando…' : 'Consultar'}
              </Botao>
              <p className="mt-4 text-[13px] text-tinta-soft">Seus dados são usados apenas para esta consulta.</p>
            </form>
          )}
        </Cartao>
      </div>
    </div>
  )
}

function Retorno({
  icone,
  titulo,
  texto,
  acao,
  aoAgir,
}: {
  icone: ReactNode
  titulo: string
  texto: string
  acao: string
  aoAgir: () => void
}) {
  return (
    <div role="alert">
      <span className="grid size-11 place-items-center rounded-full bg-bege-50 text-petroleo">{icone}</span>
      <h2 className="mt-5 text-[1.75rem]">{titulo}</h2>
      <p className="mt-2 text-[15px] text-tinta-soft">{texto}</p>
      <Botao className="mt-7 w-full" onClick={aoAgir}>
        {acao}
      </Botao>
    </div>
  )
}

function Resultado({ dados, aoVoltar }: { dados: EncaminhamentoPublico; aoVoltar: () => void }) {
  const info = NIVEL_PUBLICO[dados.fila]
  return (
    <div className="anim-subir mx-auto max-w-6xl px-4 py-10 sm:px-6 md:py-14">
      <button
        onClick={aoVoltar}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-petroleo hover:underline"
      >
        <ArrowLeft size={15} /> Nova consulta
      </button>

      <header className="mt-6 border-b border-linha pb-7">
        <p className="text-sm font-medium text-oceano">Encaminhamento de</p>
        <h1 className="mt-1 text-[2.6rem] sm:text-[3.4rem]">{dados.nome}</h1>
        <p className="mt-2 text-[17px]">
          {dados.procedimento} <span className="text-tinta-soft">· {dados.especialidade}</span>
        </p>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Cartao className="p-6 sm:p-7">
            <h2 className="text-2xl">Prioridade</h2>
            <div className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-4">
              <div>
                <p className="text-[13px] text-tinta-soft">Nível</p>
                <span
                  className={cx(
                    'tabular mt-1 inline-block rounded-md px-2.5 py-1 text-sm font-semibold ring-1 ring-inset',
                    TOM_FILA[dados.fila].selo,
                  )}
                >
                  Nível {info.nivel} de 7
                </span>
              </div>
              <div>
                <p className="text-[13px] text-tinta-soft">Sua posição na fila</p>
                <p className="tabular font-titulo text-4xl font-bold leading-none text-petroleo">{dados.posicao}º</p>
              </div>
            </div>
            <p className="mt-3 text-[15px]">{info.texto}</p>
            {dados.revisao && (
              <p className="mt-4 border-l-2 border-agua pl-3 text-[15px] text-tinta">
                Sua prioridade foi revisada em {formatarData(dados.revisao.data)} após {dados.revisao.motivo}.
              </p>
            )}
            <Link
              to="/como-funciona"
              className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-petroleo underline-offset-4 hover:underline"
            >
              Entenda como a prioridade é definida <ArrowRight size={15} />
            </Link>
          </Cartao>

          <Cartao className="p-6 sm:p-7">
            <h2 className="text-2xl">Seu encaminhamento</h2>
            <dl className="mt-4 grid gap-x-8 sm:grid-cols-2">
              <Dado termo="Situação" valor="Na fila de espera" />
              <Dado termo="Tempo de espera" valor={`${dados.diasEspera} dias`} />
              <Dado termo="Encaminhado em" valor={formatarData(dados.dataEncaminhamento)} />
              <Dado termo="Última atualização" valor={formatarData(dados.ultimaAtualizacao)} />
            </dl>
            <div className="mt-5 rounded-lg bg-nevoa-50 px-4 py-3 text-sm">
              <span className="font-semibold text-petroleo">Previsão da cirurgia: </span>
              será exibida quando houver dados confiáveis.
            </div>
          </Cartao>
        </div>

        <aside className="space-y-6">
          <Cartao className="border-bege bg-bege-50/60 p-6">
            <h2 className="text-2xl">Próximos passos</h2>
            <ul className="mt-3 space-y-3 text-[15px]">
              <li>Mantenha seus dados de contato atualizados na sua unidade de saúde.</li>
              <li>Se seus sintomas piorarem, procure sua unidade de saúde. Novos atendimentos são considerados na revisão da prioridade.</li>
            </ul>
          </Cartao>
        </aside>
      </div>
    </div>
  )
}

function Dado({ termo, valor }: { termo: string; valor: string }) {
  return (
    <div className="border-b border-linha py-3">
      <dt className="text-[13px] text-tinta-soft">{termo}</dt>
      <dd className="tabular mt-0.5 font-medium">{valor}</dd>
    </div>
  )
}
