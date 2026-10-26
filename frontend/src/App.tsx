import { useEffect } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { PublicoLayout } from './layouts/PublicoLayout'
import { ProfissionalLayout } from './layouts/ProfissionalLayout'
import { Consulta } from './pages/publico/Consulta'
import { ComoFunciona } from './pages/publico/ComoFunciona'
import { Pipeline } from './pages/publico/Pipeline'
import { Entrar } from './pages/profissional/Entrar'
import { Fila } from './pages/profissional/Fila'
import { Paciente } from './pages/profissional/Paciente'
import { RevisaoHumana } from './pages/profissional/RevisaoHumana'
import { VisaoGeral } from './pages/profissional/VisaoGeral'
import { RotaProtegida } from './store/auth'

const TITULOS: [RegExp, string][] = [
  [/^\/como-funciona/, 'Como funciona · Pulso'],
  [/^\/pipeline/, 'O pipeline por dentro · Pulso'],
  [/^\/profissional\/entrar/, 'Entrada profissional · Pulso'],
  [/^\/profissional\/fila/, 'Fila priorizada · Pulso'],
  [/^\/profissional\/pacientes/, 'Paciente · Pulso'],
  [/^\/profissional\/visao/, 'Visão geral · Pulso'],
  [/^\/profissional\/revisao/, 'Revisão humana · Pulso'],
  [/^\/$/, 'Acompanhe sua cirurgia · Pulso'],
]

function AoNavegar() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
    document.title = TITULOS.find(([re]) => re.test(pathname))?.[1] ?? 'Pulso'
  }, [pathname])
  return null
}

export default function App() {
  return (
    <>
      <AoNavegar />
      <Routes>
        <Route element={<PublicoLayout />}>
          <Route index element={<Consulta />} />
          <Route path="como-funciona" element={<ComoFunciona />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="*" element={<NaoEncontrada />} />
        </Route>

        <Route path="profissional/entrar" element={<Entrar />} />
        <Route
          path="profissional"
          element={
            <RotaProtegida>
              <ProfissionalLayout />
            </RotaProtegida>
          }
        >
          <Route index element={<Navigate to="visao" replace />} />
          <Route path="visao" element={<VisaoGeral />} />
          <Route path="fila" element={<Fila />} />
          <Route path="pacientes/:id" element={<Paciente />} />
          <Route path="revisao" element={<RevisaoHumana />} />
        </Route>
      </Routes>
    </>
  )
}

function NaoEncontrada() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
      <h1 className="text-5xl">Página não encontrada</h1>
      <Link to="/" className="mt-6 inline-block text-sm font-semibold text-petroleo hover:underline">
        Voltar ao início
      </Link>
    </div>
  )
}
