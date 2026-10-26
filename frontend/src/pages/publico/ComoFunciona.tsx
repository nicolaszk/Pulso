import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

const ETAPAS = [
  {
    titulo: 'Avaliação médica',
    texto: 'A equipe médica avalia sua condição clínica e registra a indicação da cirurgia.',
  },
  {
    titulo: 'Priorização clínica',
    texto:
      'A fila considera a urgência de cada caso, e não apenas a ordem de chegada. Diagnósticos graves, como câncer, têm a prioridade garantida pelas regras de regulação.',
  },
  {
    titulo: 'Revisão profissional',
    texto:
      'Atendimentos de urgência, exames e mudanças nos sintomas podem indicar uma nova prioridade. Toda alteração é revisada por um médico regulador.',
  },
]

export function ComoFunciona() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 md:py-20">
      <div className="max-w-2xl">
        <h1 className="text-[2.75rem] sm:text-6xl">Como a fila é organizada</h1>
        <p className="mt-5 text-[17px] text-tinta-soft">
          Quem precisa operar primeiro é definido pela condição clínica de cada pessoa, e essa avaliação é revista
          enquanto você aguarda.
        </p>
      </div>

      <ol className="mt-14 grid gap-10 md:grid-cols-3 md:gap-8">
        {ETAPAS.map((e, i) => (
          <li key={e.titulo} className="border-t-2 border-petroleo pt-5">
            <span className="font-titulo text-5xl font-semibold leading-none text-agua" aria-hidden="true">
              {String(i + 1).padStart(2, '0')}
            </span>
            <h2 className="mt-4 text-[1.75rem]">{e.titulo}</h2>
            <p className="mt-2 text-[15px]">{e.texto}</p>
          </li>
        ))}
      </ol>

      <div className="mt-16 flex flex-col items-start gap-4 border-t border-linha pt-8 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-xl text-[15px] text-tinta-soft">
          Se seus sintomas piorarem enquanto aguarda, procure sua unidade de saúde. O atendimento fica registrado e
          entra na revisão da sua prioridade.
        </p>
        <Link
          to="/"
          className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-lg bg-petroleo px-5 text-sm font-semibold text-white hover:bg-petroleo-900"
        >
          Consultar minha cirurgia <ArrowRight size={16} />
        </Link>
      </div>

      <p className="mt-10 text-[13px] text-tinta-soft">
        Quer ver como o motor funciona por dentro?{' '}
        <Link to="/pipeline" className="font-semibold text-petroleo hover:underline">
          O pipeline, passo a passo
        </Link>
      </p>
    </div>
  )
}
