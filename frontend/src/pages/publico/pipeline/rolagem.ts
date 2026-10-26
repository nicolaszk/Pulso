// Ganchos de rolagem da página do pipeline: progresso das cenas, tamanho e canvas.
import { useEffect, useRef, useState, type RefObject } from 'react'

export const limitar = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v))
export const mix = (a: number, b: number, t: number) => a + (b - a) * t
/** Fração de p dentro do trecho [a, b] da cena (0 antes, 1 depois). */
export const trecho = (p: number, a: number, b: number) => limitar((p - a) / (b - a))
export const suave = (t: number) => t * t * (3 - 2 * t)
export const saida = (t: number) => 1 - Math.pow(1 - t, 3)

export const br = (n: number) => Math.round(n).toLocaleString('pt-BR')

export function useMenosMovimento() {
  const consulta = '(prefers-reduced-motion: reduce)'
  const [r, setR] = useState(() => window.matchMedia(consulta).matches)
  useEffect(() => {
    const mq = window.matchMedia(consulta)
    const on = () => setR(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return r
}

export interface EstadoCena {
  /** 0..1 ao longo da cena */
  p: number
  /** último [data-passo] que passou de 60% da tela (99 com movimento reduzido) */
  passo: number
}

/**
 * Progresso de uma cena com palco fixo (sticky): p = 0 quando o topo da seção chega ao topo
 * da tela, 1 quando o fim da seção chega ao fim da tela. Com movimento reduzido, fica no fim.
 */
export function useCena(ref: RefObject<HTMLElement | null>): EstadoCena {
  const calmo = useMenosMovimento()
  const [e, setE] = useState<EstadoCena>(calmo ? { p: 1, passo: 99 } : { p: 0, passo: 0 })
  useEffect(() => {
    if (calmo) {
      setE({ p: 1, passo: 99 })
      return
    }
    let raf = 0
    const medir = () => {
      raf = 0
      const el = ref.current
      if (!el) return
      const vh = window.innerHeight
      const r = el.getBoundingClientRect()
      const total = r.height - vh
      const p = total <= 0 ? (r.top <= 0 ? 1 : 0) : limitar(-r.top / total)
      let passo = 0
      el.querySelectorAll<HTMLElement>('[data-passo]').forEach((ps, i) => {
        if (ps.getBoundingClientRect().top < vh * 0.6) passo = i
      })
      setE((v) => (Math.abs(v.p - p) < 0.0004 && v.passo === passo ? v : { p, passo }))
    }
    const agendar = () => {
      if (!raf) raf = requestAnimationFrame(medir)
    }
    medir()
    window.addEventListener('scroll', agendar, { passive: true })
    window.addEventListener('resize', agendar)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', agendar)
      window.removeEventListener('resize', agendar)
    }
  }, [ref, calmo])
  return e
}

/** Tamanho de um elemento, atualizado no resize. */
export function useTamanho(ref: RefObject<HTMLElement | null>) {
  const [t, setT] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => setT({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return t
}

/** Vira true uma vez, quando o elemento entra na tela. */
export function useVisto(ref: RefObject<Element | null>, margem = '0px 0px -20% 0px') {
  const [visto, setVisto] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || visto) return
    const io = new IntersectionObserver(
      (es) => {
        if (es.some((e) => e.isIntersecting)) {
          setVisto(true)
          io.disconnect()
        }
      },
      { rootMargin: margem },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [ref, margem, visto])
  return visto
}

export type Desenho = (ctx: CanvasRenderingContext2D, w: number, h: number) => void

/** Canvas nítido (devicePixelRatio) que redesenha quando `desenhar` muda ou o tamanho muda. */
export function useTela(desenhar: Desenho) {
  const ref = useRef<HTMLCanvasElement>(null)
  const atual = useRef(desenhar)
  atual.current = desenhar
  const pintar = useRef<() => void>(() => {})

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    pintar.current = () => {
      const w = cv.clientWidth
      const h = cv.clientHeight
      if (!w || !h) return
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr)
        cv.height = Math.round(h * dpr)
      }
      const ctx = cv.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      atual.current(ctx, w, h)
    }
    const ro = new ResizeObserver(() => pintar.current())
    ro.observe(cv)
    document.fonts?.ready.then(() => pintar.current()) // os textos do canvas usam a fonte da página
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    pintar.current()
  }, [desenhar])

  return ref
}
