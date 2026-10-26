// 06 · Saída: a fila recomendada, nível a nível, cada posição com o seu recibo.
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Check } from 'lucide-react'
import { SeloFila } from '../../../../components/ui'
import { ORDEM_FILAS, type FilaCodigo } from '../../../../data/fila'
import { COR, PONTOS, carregarRecibos, corNivel, type Recibo } from '../dados'
import { useTamanho, useTela, useVisto } from '../rolagem'

// Os 897 na ordem da fila recomendada (como se todos os pedidos fossem aprovados).
const FINAL = PONTOS.filter((p) => p.fim >= 0).sort((a, b) => a.rec - b.rec)
const ULTIMO_ONCO = Math.max(...FINAL.filter((p) => p.onco).map((p) => p.rec)) // 265
const POS_HEROI = 37
/** Primeira posição de cada nível. */
const INICIO_NIVEL = ORDEM_FILAS.map((_, f) => FINAL.findIndex((p) => p.fim === f) + 1)

function grade(w: number) {
  const margem = w >= 640 ? 190 : 0 // à direita, os rótulos dos níveis
  const por = w >= 900 ? 36 : w >= 560 ? 30 : 20
  const pas = Math.min((w - margem) / por, 21)
  const linhas = Math.ceil(FINAL.length / por)
  return { por, pas, linhas, margem, x0: 0, y0: 26, h: 26 + linhas * pas + 34 }
}

/** A justificativa do motor vira linhas do recibo: evidências, datas, alertas. */
function partes(j: string) {
  return j.split(' | ').slice(1).flatMap((s) => s.split('; '))
}

export function Saida() {
  const ref = useRef<HTMLElement>(null)
  const visto = useVisto(ref, '0px 0px 60% 0px')
  const [recibos, setRecibos] = useState<Recibo[] | null>(null)
  const [pos, setPos] = useState(POS_HEROI)

  useEffect(() => {
    if (visto && !recibos) carregarRecibos().then(setRecibos)
  }, [visto, recibos])

  const tela = useTela(
    useCallback(
      (ctx: CanvasRenderingContext2D, cw: number) => {
        const { por, pas, x0, y0, linhas, margem } = grade(cw)
        const r = pas * 0.32
        const xy = (i: number) => [x0 + (i % por) * pas + pas / 2, y0 + Math.floor(i / por) * pas + pas / 2] as const
        FINAL.forEach((pt, i) => {
          const [x, y] = xy(i)
          ctx.beginPath()
          ctx.arc(x, y, r, 0, Math.PI * 2)
          ctx.fillStyle = corNivel(pt.fim)
          ctx.fill()
          if (pt.onco) {
            ctx.beginPath()
            ctx.arc(x, y, r + 1.7, 0, Math.PI * 2)
            ctx.strokeStyle = COR.petroleo900
            ctx.lineWidth = 1
            ctx.stroke()
          }
        })

        ctx.font = "600 11px Montserrat, system-ui, sans-serif"
        ctx.textBaseline = 'middle'
        const xr = x0 + por * pas + 14

        // onde começa cada nível
        if (margem) {
          ORDEM_FILAS.forEach((f, k) => {
            const i = INICIO_NIVEL[k] - 1
            const y = y0 + Math.floor(i / por) * pas + pas / 2
            ctx.fillStyle = corNivel(k)
            ctx.fillRect(xr, y - 1, 10, 2)
            ctx.fillText(`${f} · ${INICIO_NIVEL[k]}`, xr + 16, y)
          })
        }

        // regra de ouro: degrau entre o último com câncer e o resto
        const lin = Math.floor(ULTIMO_ONCO / por)
        const col = ULTIMO_ONCO % por
        const yA = y0 + lin * pas
        const yB = yA + pas
        const xC = x0 + col * pas
        ctx.strokeStyle = COR.petroleo
        ctx.lineWidth = 1.6
        ctx.setLineDash([4, 3])
        ctx.beginPath()
        ctx.moveTo(x0, yB)
        ctx.lineTo(xC, yB)
        ctx.lineTo(xC, yA)
        ctx.lineTo(x0 + por * pas + (margem ? 8 : 0), yA)
        ctx.stroke()
        ctx.setLineDash([])

        ctx.fillStyle = COR.tintaSoft
        ctx.textAlign = 'left'
        ctx.fillText('1', x0 + 2, y0 - 12)
        ctx.textAlign = 'right'
        ctx.fillText('897', x0 + por * pas, y0 + linhas * pas + 14)
        ctx.textAlign = 'left'

        // seleção
        const [sx, sy] = xy(pos - 1)
        ctx.beginPath()
        ctx.arc(sx, sy, r + 5, 0, Math.PI * 2)
        ctx.strokeStyle = COR.petroleo
        ctx.lineWidth = 1.8
        ctx.stroke()
      },
      [pos],
    ),
  )

  const escolher = (e: PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const { por, pas, x0, y0 } = grade(rect.width)
    const c = Math.floor((e.clientX - rect.left - x0) / pas)
    const l = Math.floor((e.clientY - rect.top - y0) / pas)
    const i = l * por + c
    if (c >= 0 && c < por && l >= 0 && i < FINAL.length) setPos(i + 1)
  }

  // a altura do canvas sai da largura do próprio canvas (sem o padding da caixa), a mesma usada no desenho
  const { w } = useTamanho(tela)
  const g = useMemo(() => grade(w || 900), [w])

  const rec = recibos?.[pos - 1]
  return (
    <section ref={ref} id="saida" className="relative py-20 md:py-28" data-traco="calmo" aria-labelledby="pl-saida">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <p className="pl-num">06 · Saída</p>
        <h2 id="pl-saida" className="text-[2.25rem] sm:text-[2.75rem]">897 posições, cada uma com recibo.</h2>
        <p className="mt-3 max-w-2xl text-[16px] text-tinta-soft">
          A fila recomendada, nível a nível. A justificativa de cada posição sai do motor, com evidências e datas. O
          LLM (gemma4:e4b) só reescreve o texto, e uma checagem rejeita qualquer número, data ou termo que não esteja
          nos fatos.
        </p>

        <div className="mt-10 grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_21rem]">
          <div className="rounded-xl border border-linha bg-white p-4 sm:p-5">
            <canvas
              ref={tela}
              className="block w-full cursor-crosshair touch-manipulation"
              style={{ height: g.h }}
              onPointerMove={(e) => e.pointerType === 'mouse' && escolher(e)}
              onPointerDown={escolher}
              role="img"
              aria-label={`Fila recomendada com 897 pacientes, colorida por nível. Todos os pacientes com câncer estão até a posição ${ULTIMO_ONCO}.`}
            />
            {!g.margem && (
              // sem margem para os rótulos no canvas: onde começa cada nível, abaixo
              <ul className="mt-3 flex flex-wrap gap-x-3 gap-y-1.5 text-[12px] text-tinta-soft">
                {ORDEM_FILAS.map((f, k) => (
                  <li key={f} className="tabular flex items-center gap-1">
                    <SeloFila f={f} compacto /> {INICIO_NIVEL[k]}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 flex items-start gap-2 text-[13px] text-tinta-soft">
              <Check size={16} className="mt-0.5 shrink-0 text-sucesso" />
              <span>
                Regra de ouro: o último paciente com CID C* está na posição {ULTIMO_ONCO}; abaixo da linha tracejada
                não há CID C*. Conferido pelo verificador oficial do desafio.
              </span>
            </p>
          </div>

          <aside className="pl-recibo lg:sticky lg:top-6" aria-live="polite">
            <label className="flex items-center gap-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-tinta-soft">
              Posição
              <input
                type="number"
                min={1}
                max={FINAL.length}
                value={pos}
                onChange={(e) => {
                  const v = Math.round(Number(e.target.value))
                  if (v >= 1 && v <= FINAL.length) setPos(v)
                }}
                className="tabular min-h-9 w-24 rounded-lg border border-linha bg-white px-2.5 text-[15px] font-semibold normal-case tracking-normal text-tinta outline-none focus:border-oceano focus:ring-2 focus:ring-oceano/25"
              />
            </label>
            {rec ? (
              <>
                <p className="pl-mono mt-4 border-b border-dashed border-linha pb-3 text-[12px] font-semibold">
                  RECIBO · POSIÇÃO {String(rec[0]).padStart(4, '0')}
                  <br />
                  {rec[1]}
                </p>
                <div className="mt-3">
                  <SeloFila f={rec[2] as FilaCodigo} nome />
                </div>
                <p className="mt-2 text-[13px] text-tinta-soft">
                  {rec[4]} · CID {rec[3]}
                  {pos === POS_HEROI && <b className="text-petroleo"> · a 621</b>}
                </p>
                <ul className="pl-mono mt-3 space-y-1.5 text-[12px] leading-relaxed">
                  {partes(rec[5]).map((l, i) => (
                    <li key={i} className="relative pl-3 before:absolute before:left-0 before:content-['·']">
                      {l}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="mt-4 text-[13px] text-tinta-soft">Carregando recibos…</p>
            )}
          </aside>
        </div>

        <div className="mx-auto mt-20 max-w-3xl text-center">
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              to="/profissional/entrar"
              className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-petroleo px-5 text-sm font-semibold text-white hover:bg-petroleo-900"
            >
              Entrar na área profissional <ArrowRight size={16} />
            </Link>
            <Link
              to="/"
              className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-petroleo/40 bg-white px-5 text-sm font-semibold text-petroleo hover:border-petroleo hover:bg-nevoa-50"
            >
              Ver como o paciente consulta
            </Link>
          </div>
          <ul className="mt-12 space-y-1.5 border-t border-linha pt-6 text-[13px] text-tinta-soft">
            <li>
              <code className="pl-mono rounded bg-nevoa-50 px-1.5 py-0.5 text-tinta">docker compose up -d --build</code> sobe o
              Postgres 16 e a API na porta 8000.
            </li>
            <li>A ordem é determinística. O LLM só reescreve as explicações: 1.025 textos conferidos e guardados.</li>
            <li>Dados sintéticos do desafio · 9ª Hackatona de Engenharia de Software 2026 · Fin-x · PUCRS · Hospital São Lucas</li>
          </ul>
        </div>
      </div>
    </section>
  )
}
