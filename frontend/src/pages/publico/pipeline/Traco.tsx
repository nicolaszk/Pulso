// O traço: um ECG fixo na margem esquerda que acompanha a rolagem pelas seções.
// Cada elemento com [data-traco] dentro de `papel` vira um marco, na ordem da página: uma batida no traço
// e um número clicável (lido do .pl-num do marco, ex.: "02 · Motor"). Seção nova com data-traco entra sozinha.
// O valor de data-traco muda a batida: "duas" (batida dupla), "faixas" (o traço se abre nos 8 níveis até o
// próximo marco), "calmo" (batida menor). Qualquer outro valor desenha uma batida simples.
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { cx } from '../../../components/ui'
import { ORDEM_FILAS } from '../../../data/fila'
import { corNivel } from './dados'
import { limitar, useMenosMovimento, useTamanho } from './rolagem'

interface Marco {
  el: HTMLElement
  tipo: string
  num: string
  titulo: string
}

const X = 40 // eixo do traço dentro do svg; à esquerda ficam os números
const LARG = 64
const PAD = 10

// Um complexo PQRST deitado: [ao longo do eixo, para o lado], relativos ao início da batida (58px).
const BATIDA: [number, number][] = [
  [0, 0], [5, 3], [10, 0], [20, 0], [23, -4], [27, 17], [31, -11], [34, 0], [46, 0], [52, 6], [58, 0],
]
const COMPR = 58

const ponto = (a: number, c = 0) => `${(X + c).toFixed(1)} ${a.toFixed(1)}`
const batida = (a0: number, esc: number, amp: number) =>
  BATIDA.map(([da, dc]) => `L${ponto(a0 + da * esc, dc * amp)}`).join('')

/** Posição de cada marco no traço (e do fim), espaçados por igual. */
function posicoes(n: number, altura: number) {
  const passo = (altura - 2 * PAD) / Math.max(1, n)
  return Array.from({ length: n + 1 }, (_, i) => PAD + i * passo)
}

function construir(marcos: Marco[], ys: number[]) {
  let d = `M${ponto(ys[0])}`
  const faixas: string[] = []
  marcos.forEach((m, i) => {
    const a = ys[i] + 6
    const seg = ys[i + 1] - ys[i] - 10
    const duas = m.tipo === 'duas'
    const leque = m.tipo === 'faixas'
    // na batida dupla cabem duas; no leque, a batida encolhe para sobrar trecho para os 8 níveis
    const esc = limitar((seg - 8) / (COMPR * (duas ? 2 : leque ? 1.8 : 1)), 0.3, 1)
    const amp = (m.tipo === 'calmo' ? 0.7 : 1) * Math.min(1, esc + 0.2)
    d += `L${ponto(a)}` + batida(a, esc, amp)
    let fim = a + COMPR * esc
    if (duas) {
      d += batida(fim, esc, amp)
      fim += COMPR * esc
    }
    const b = ys[i + 1] - 4
    if (leque && b - fim > 26) {
      // o traço se abre nos 8 níveis e volta a ser um só antes do próximo marco
      const curva = Math.min(12, (b - fim) / 3)
      ORDEM_FILAS.forEach((_, k) => {
        const dc = (k - 3.5) * 2.6
        faixas.push(
          `M${ponto(fim)}C${ponto(fim + curva * 0.6)} ${ponto(fim + curva * 0.4, dc)} ${ponto(fim + curva, dc)}` +
            `L${ponto(b - curva, dc)}C${ponto(b - curva * 0.4, dc)} ${ponto(b - curva * 0.6)} ${ponto(b)}`,
        )
      })
      d += `L${ponto(fim)}M${ponto(b)}`
    }
  })
  return { d: d + `L${ponto(ys[ys.length - 1])}`, faixas }
}

function lerMarcos(papel: HTMLElement): Marco[] {
  return Array.from(papel.querySelectorAll<HTMLElement>('[data-traco]')).map((el, i) => {
    const rotulo = el.querySelector('.pl-num')?.textContent ?? ''
    const [num, ...resto] = rotulo.split('·').map((s) => s.trim())
    const titulo =
      resto.join(' · ') || el.querySelector('h2')?.textContent?.trim() || el.getAttribute('aria-label') || ''
    return { el, tipo: el.dataset.traco ?? '', num: num || String(i + 1).padStart(2, '0'), titulo }
  })
}

export function Traco({ papel }: { papel: RefObject<HTMLDivElement | null> }) {
  const caixa = useRef<HTMLElement>(null)
  const recorte = useRef<SVGRectElement>(null)
  const ponta = useRef<SVGGElement>(null)
  const topos = useRef<number[]>([])
  const { h: altura } = useTamanho(caixa)
  const [marcos, setMarcos] = useState<Marco[]>([])
  const [ativo, setAtivo] = useState(0)
  const calmo = useMenosMovimento()

  // onde cada marco começa na página (e onde o papel termina)
  useEffect(() => {
    const el = papel.current
    if (!el) return
    const medir = () => {
      const lidos = lerMarcos(el)
      const y = (n: HTMLElement) => n.getBoundingClientRect().top + window.scrollY
      topos.current = [...lidos.map((m) => y(m.el)), el.getBoundingClientRect().bottom + window.scrollY]
      setMarcos((v) =>
        v.length === lidos.length && v.every((m, i) => m.el === lidos[i].el && m.num === lidos[i].num) ? v : lidos,
      )
      window.dispatchEvent(new Event('pl-traco'))
    }
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(el)
    return () => ro.disconnect()
  }, [papel])

  const ys = useMemo(() => (altura ? posicoes(marcos.length, altura) : []), [marcos.length, altura])

  useEffect(() => {
    const el = papel.current
    const nav = caixa.current
    if (!el || !nav || !ys.length) return
    let raf = 0
    const desenhar = () => {
      raf = 0
      const t = topos.current
      const n = t.length - 1
      if (n < 1) return
      const vh = window.innerHeight
      const ref = window.scrollY + vh * 0.5
      let i = 0
      while (i < n - 1 && ref >= t[i + 1]) i++
      let f = limitar((ref - t[i]) / Math.max(1, t[i + 1] - t[i]))
      if (window.scrollY + vh >= document.documentElement.scrollHeight - 4) {
        i = n - 1
        f = 1
      }
      const y = ys[i] + f * (ys[i + 1] - ys[i])
      recorte.current?.setAttribute('height', String(y))
      ponta.current?.setAttribute('transform', `translate(${X} ${y})`)
      const r = el.getBoundingClientRect()
      nav.dataset.visivel = String(r.top < vh * 0.6 && r.bottom > vh * 0.3)
      setAtivo(i)
    }
    const agendar = () => {
      if (!raf) raf = requestAnimationFrame(desenhar)
    }
    desenhar()
    window.addEventListener('scroll', agendar, { passive: true })
    window.addEventListener('resize', agendar)
    window.addEventListener('pl-traco', agendar)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', agendar)
      window.removeEventListener('resize', agendar)
      window.removeEventListener('pl-traco', agendar)
    }
  }, [papel, ys])

  const { d, faixas } = useMemo(() => (ys.length ? construir(marcos, ys) : { d: '', faixas: [] }), [marcos, ys])

  const ir = (el: HTMLElement) => el.scrollIntoView({ behavior: calmo ? 'auto' : 'smooth', block: 'start' })

  return (
    <nav ref={caixa} className="pl-traco" aria-label="Seções do pipeline" data-visivel="false">
      {d && (
        <svg width={LARG} height={altura} aria-hidden="true">
          <defs>
            <clipPath id="pl-traco-recorte">
              <rect ref={recorte} x="0" y="0" width={LARG} height="0" />
            </clipPath>
          </defs>
          <path className="pl-traco-guia" d={d} />
          {faixas.map((f, i) => (
            <path key={i} className="pl-traco-guia" d={f} />
          ))}
          <g clipPath="url(#pl-traco-recorte)">
            <path className="pl-traco-linha" d={d} />
            {faixas.map((f, i) => (
              <path key={i} className="pl-traco-faixa" d={f} stroke={corNivel(i)} />
            ))}
          </g>
          {marcos.map((_, i) => (
            <circle key={i} className={cx('pl-traco-no', i <= ativo && 'passou')} cx={X} cy={ys[i]} r="3" />
          ))}
          <g ref={ponta} transform={`translate(${X} ${ys[0]})`}>
            <circle className="pl-traco-eco" r="4" />
            <circle className="pl-traco-ponta" r="4" />
          </g>
        </svg>
      )}
      {ys.length > 0 && (
        <ol>
          {marcos.map((m, i) => (
            <li key={i} style={{ top: ys[i] }}>
              <button
                type="button"
                className={cx('pl-traco-marco', i < ativo && 'passou')}
                aria-current={i === ativo ? 'step' : undefined}
                title={m.titulo}
                onClick={() => ir(m.el)}
              >
                {m.num}
                <span className="sr-only"> · {m.titulo}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </nav>
  )
}
