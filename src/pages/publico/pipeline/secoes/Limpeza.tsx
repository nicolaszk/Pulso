// 01 · Entrada e limpeza: o que sai do fluxo vai para uma bandeja com o motivo. Nenhuma linha é apagada.
import { useRef } from 'react'
import { br, mix, saida, trecho, useCena } from '../rolagem'

interface Bandeja {
  nome: string
  n: number
  x: number
  lado: -1 | 1
  de: 'pedidos' | 'eventos'
}

const BANDEJAS: Bandeja[] = [
  { nome: 'Duplicatas', n: 22, x: 20, lado: -1, de: 'pedidos' },
  { nome: 'Saídas', n: 17, x: 134, lado: -1, de: 'pedidos' },
  { nome: 'Quarentena', n: 9, x: 326, lado: 1, de: 'eventos' },
  { nome: 'Repetidos', n: 7, x: 440, lado: 1, de: 'eventos' },
]
const TOTAL_FICHAS = BANDEJAS.reduce((s, b) => s + b.n, 0) // 55
const POR_LINHA = 8
const FUNDO_BANDEJA = 446

// Cada ficha sai da parede do filtro e cai no seu lugar na bandeja.
const FICHAS = BANDEJAS.flatMap((b, ib) =>
  Array.from({ length: b.n }, (_, j) => {
    const sx = b.lado < 0 ? 230 : 330
    const ex = b.x + 9 + (j % POR_LINHA) * 11.4
    const ey = FUNDO_BANDEJA - 9 - Math.floor(j / POR_LINHA) * 8.5
    return { ib, sx, sy: 262, cx: mix(sx, ex, 0.75), cy: 250, ex, ey }
  }),
)

const ARQUIVOS = [
  { nome: 'fila_cirurgica.csv', n: '941 linhas', x: 14 },
  { nome: 'eventos_clinicos.csv', n: '1.505 linhas', x: 198 },
  { nome: 'procedimentos.csv', n: '23 linhas', x: 382 },
]

const RELATORIO: [string, string][] = [
  ['816', 'CIDs normalizados: K409 e K40.9 são o mesmo código.'],
  ['50', 'registros com município reescrito: 62 grafias viram 38 municípios.'],
  ['22', 'pedidos duplicados fundidos no mais antigo, com textos e eventos.'],
  ['17', 'saídas achadas nas observações: desistência, cirurgia em outro serviço.'],
  ['9', 'eventos em quarentena: apontavam para pedidos que não existem.'],
  ['7', 'eventos repetidos (mesmo conteúdo, id diferente) descartados.'],
]

export function Limpeza() {
  const ref = useRef<HTMLElement>(null)
  const { p } = useCena(ref)
  const correcoes = trecho(p, 0.05, 0.16)

  const caidas = BANDEJAS.map(() => 0)
  const fichas = FICHAS.map((f, g) => {
    const ini = 0.12 + (g / TOTAL_FICHAS) * 0.55
    const t = saida(trecho(p, ini, ini + 0.08))
    if (t >= 1) caidas[f.ib]++
    const u = 1 - t
    return { ...f, t, x: u * u * f.sx + 2 * u * t * f.cx + t * t * f.ex, y: u * u * f.sy + 2 * u * t * f.cy + t * t * f.ey }
  })
  const pedidos = 941 - caidas[0] - caidas[1]
  const eventos = 1505 - caidas[2] - caidas[3]

  return (
    <section ref={ref} id="limpeza" className="pl-cena" data-traco="plano" aria-labelledby="pl-limpeza">
      <div className="pl-palco">
        <div className="pl-vis">
          <svg
            className="pl-peneira"
            viewBox="0 0 560 590"
            role="img"
            aria-label={`Os três arquivos passam por um filtro. Ficam em bandejas: ${BANDEJAS.map((b) => `${b.nome} ${b.n}`).join(', ')}. Saem ${pedidos} pedidos ativos e ${eventos} eventos válidos.`}
          >
            {ARQUIVOS.map((a) => (
              <g key={a.nome} transform={`translate(${a.x} 6)`}>
                <rect className="pl-arq" width="164" height="46" rx="8" />
                <text className="pl-svg-mono" x="12" y="20">{a.nome}</text>
                <text className="pl-svg-mono suave" x="12" y="36">{a.n}</text>
                <path className="pl-fio" d={`M82 46 C82 92 ${280 - a.x} 92 ${280 - a.x} 134`} />
              </g>
            ))}

            <path className="pl-funil" d="M140 140 L420 140 L298 300 L262 300 Z" />
            {[170, 200, 230, 260, 290, 320, 350, 380, 410].map((x) => (
              <path key={x} className="pl-dobra" d={`M${x} 140 L${mix(x, 280, 0.86)} 296`} />
            ))}
            <g style={{ opacity: correcoes }}>
              <text className="pl-svg-mono forte" x="280" y="172" textAnchor="middle">✓ 816 CIDs normalizados</text>
              <text className="pl-svg-mono forte" x="280" y="194" textAnchor="middle">✓ 62 grafias → 38 municípios</text>
            </g>

            <path className="pl-fluxo" d="M280 300 L280 498" />

            {BANDEJAS.map((b, i) => (
              <g key={b.nome}>
                <path className="pl-bandeja" d={`M${b.x} 398 L${b.x + 4} ${FUNDO_BANDEJA} L${b.x + 98} ${FUNDO_BANDEJA} L${b.x + 102} 398`} />
                <text className="pl-svg-texto" x={b.x + 51} y="470" textAnchor="middle">{b.nome}</text>
                <text className="pl-svg-num" x={b.x + 51} y="492" textAnchor="middle">{caidas[i]}</text>
              </g>
            ))}

            {fichas.map(
              (f, g) =>
                f.t > 0 && (
                  <rect key={g} className={`pl-ficha ${BANDEJAS[f.ib].de}`} x={f.x - 4.5} y={f.y - 3} width="9" height="6" rx="1.5" />
                ),
            )}

            <g transform="translate(140 508)">
              <rect className="pl-saida" width="280" height="76" rx="10" />
              <text className="pl-svg-num grande" x="22" y="36">{br(pedidos)}</text>
              <text className="pl-svg-texto suave" x="22" y="58" textAnchor="start">pedidos ativos</text>
              <text className="pl-svg-num grande" x="150" y="36">{br(eventos)}</text>
              <text className="pl-svg-texto suave" x="150" y="58" textAnchor="start">eventos válidos</text>
            </g>
          </svg>
        </div>
      </div>

      <div className="pl-roteiro">
        <div className="pl-passo" data-passo>
          <div className="pl-cartao">
            <p className="pl-num">01 · Entrada e limpeza</p>
            <h2 id="pl-limpeza" className="text-[2.25rem] sm:text-[2.75rem]">Nenhuma linha é apagada.</h2>
            <p className="mt-3 text-[16px] text-tinta-soft">
              Os três CSVs entram sem edição manual. Cada correção fica registrada; o que sai do fluxo é guardado com
              o motivo.
            </p>
            <ul className="mt-5 divide-y divide-dashed divide-linha border-t border-dashed border-linha">
              {RELATORIO.map(([n, t]) => (
                <li key={n} className="grid grid-cols-[3rem_minmax(0,1fr)] gap-3 py-2 text-[14px]">
                  <b className="tabular text-right font-titulo text-base font-bold text-petroleo">{n}</b>
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="pl-passo" data-passo>
          <div className="pl-cartao">
            <p className="tabular font-titulo text-[2rem] font-bold leading-tight text-petroleo">941 → 902 pedidos ativos</p>
            <p className="tabular font-titulo text-[2rem] font-bold leading-tight text-petroleo">1.505 → 1.489 eventos válidos</p>
            <p className="mt-4 text-[14px] text-tinta-soft">
              As 5 saídas avisadas por telefone não saem na limpeza: chegam como eventos e viram pedidos para o
              médico. Por isso 902 pedidos entram no motor e 897 terminam na fila recomendada.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
