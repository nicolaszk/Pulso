// 02 · Motor e 03 · Eventos. Os 8 níveis ficam na tela a cena inteira: primeiro o cadastro distribui
// os 902 pedidos; depois os 1.489 eventos chegam, um por um, e cada um reavalia só aquele paciente.
import { useCallback, useRef, useState } from 'react'
import { SeloFila } from '../../../../components/ui'
import { NOME_FILA, ORDEM_FILAS, PRAZO_FILA } from '../../../../data/fila'
import { COR, EVENTOS, HEROI, PONTOS, REGRA_FILA, TIPOS_EVENTO, corNivel } from '../dados'
import { br, limitar, mix, suave, trecho, useCena, useTamanho, useTela } from '../rolagem'

const N = PONTOS.length // 902
const NE = EVENTOS.length // 1.489

/** Mudanças de nível recomendadas de cada paciente, com o índice do evento que causou. */
interface Mudanca {
  e: number
  de: number
  para: number
}
const TRAJETORIA: Mudanca[][] = PONTOS.map(() => [])
/** Nível antes do evento k, quando o evento muda o nível do paciente. */
const DE_NIVEL = new Map<number, number>()
{
  const atual = PONTOS.map((p) => p.ini)
  EVENTOS.forEach((ev, e) => {
    if (ev.paciente < 0 || ev.nivel === atual[ev.paciente]) return
    TRAJETORIA[ev.paciente].push({ e, de: atual[ev.paciente], para: ev.nivel })
    DE_NIVEL.set(e, atual[ev.paciente])
    atual[ev.paciente] = ev.nivel
  })
}

/** Somas acumuladas até o evento k (exclusivo). */
const ACUM = (() => {
  const sem = [0], abriu = [0], evid = [0], subst = [0]
  EVENTOS.forEach((e, k) => {
    sem.push(sem[k] + (e.acao === 0 ? 1 : 0))
    abriu.push(abriu[k] + (e.acao === 1 ? 1 : 0))
    evid.push(evid[k] + (e.acao === 2 ? 1 : 0))
    subst.push(subst[k] + (e.substituiu ? 1 : 0))
  })
  return { sem, abriu, evid, subst }
})()

/** Maior nível em qualquer momento, para a raia caber. */
const MAIOR = (() => {
  const c = Array(8).fill(0)
  PONTOS.forEach((p) => c[p.ini]++)
  let m = Math.max(...c)
  for (const t of TRAJETORIA.flat().sort((a, b) => a.e - b.e)) {
    c[t.de]--
    if (t.para >= 0) c[t.para]++
    m = Math.max(m, ...c)
  }
  return m
})()

// Linha do tempo da cena (p = 0..1): cadastro, chave de ordenação, regra de ouro, eventos.
const PONTOS_N: [number, number][] = [
  [0.6, 0],
  [0.7, 5], // os primeiros, um por passo de rolagem
  [0.76, 41], // até o primeiro que muda um nível (evento 41: G7 → G4), e segura nele
  [0.8, 41.95],
  [0.93, NE], // e a montagem até o fim
]
function eventosAte(p: number) {
  if (p <= PONTOS_N[0][0]) return 0
  for (let i = 1; i < PONTOS_N.length; i++) {
    const [p0, n0] = PONTOS_N[i - 1]
    const [p1, n1] = PONTOS_N[i]
    if (p <= p1) {
      const t = trecho(p, p0, p1)
      return mix(n0, n1, i === PONTOS_N.length - 1 ? t * t : t)
    }
  }
  return NE
}

const DESFECHO = ['não muda o nível', 'abre pedido para o médico', 'evidência nova num pedido aberto']
const CHAVE = 'ORDER BY nível, data_limite, sinais DESC, dor DESC, entrada'

// Complexo PQRST: u em [-0.5, 0.5] da largura, v em fração da amplitude (negativo = para cima).
const COMPLEXO: [number, number][] = [
  [-0.5, 0], [-0.38, -0.09], [-0.28, 0], [-0.1, 0], [-0.05, 0.13], [0, -1], [0.06, 0.32], [0.12, 0],
  [0.24, 0], [0.33, -0.19], [0.42, 0], [0.5, 0],
]

function geometria(w: number, h: number) {
  const fone = w < 520
  const faixaH = 112 // tira do traço, em cima
  // estreito: a linha do evento (.pl-agora) desce para baixo da caixa de pedidos e ocupa a largura toda;
  // o mesmo limite está no @container de pipeline.css
  const estreito = w < 560
  const topo = faixaH + (estreito ? 62 : 34)
  const base = 6
  const abre = fone ? 12 : 34
  const cabeca = w >= 560 ? 214 : fone ? 62 : 118
  const vao = fone ? 3 : 5
  const raiaH = (h - topo - base - vao * 7) / 8
  const x0 = abre + cabeca + 8
  const areaW = Math.max(40, w - x0 - 4)
  let R = 1
  let pas = 0
  for (let r = 1; r <= 16; r++) {
    const ps = Math.min(areaW / Math.ceil(MAIOR / r), raiaH / r)
    if (ps > pas) [R, pas] = [r, ps]
  }
  const yRaia = (f: number) => topo + f * (raiaH + vao)
  const naRaia = (f: number, j: number) => ({
    x: x0 + pas / 2 + Math.floor(j / R) * pas,
    y: yRaia(f) + (raiaH - R * pas) / 2 + pas / 2 + (j % R) * pas,
  })
  const cols = Math.ceil(Math.sqrt((N * areaW) / (h - topo - base)))
  const pg = Math.min(areaW / cols, (h - topo - base) / Math.ceil(N / cols))
  const naGrade = (i: number) => ({ x: x0 + pg / 2 + (i % cols) * pg, y: topo + pg / 2 + Math.floor(i / cols) * pg })
  return { fone, faixaH, topo, base, abre, cabeca, vao, raiaH, x0, pas, yRaia, naRaia, naGrade }
}

export function Motor() {
  const ref = useRef<HTMLElement>(null)
  const vis = useRef<HTMLDivElement>(null)
  const { p } = useCena(ref)
  const { w, h } = useTamanho(vis)
  const [foco, setFoco] = useState<number | null>(null)

  const queda = trecho(p, 0, 0.14)
  const chave = trecho(p, 0.14, 0.2) * (1 - trecho(p, 0.32, 0.36))
  const ouro = trecho(p, 0.36, 0.42) * (1 - trecho(p, 0.54, 0.58))
  const faixa = trecho(p, 0.56, 0.62)
  const n = eventosAte(p)
  const feitos = Math.min(NE, Math.floor(n + 1e-6))
  const rapido = trecho(p, 0.8, 0.86) // 0 = legível, 1 = montagem
  const dur = mix(0.9, 40, rapido) // quantos eventos dura uma mudança de nível na tela

  // Onde cada paciente está agora: nível de origem, de destino e quanto já andou.
  const conta = Array(8).fill(0)
  const estados = PONTOS.map((pt, i) => {
    let de = pt.ini
    let para = pt.ini
    let t = 1
    for (const m of TRAJETORIA[i]) {
      if (m.e >= feitos) break
      de = m.de
      para = m.para
      t = limitar((n - (m.e + 1)) / dur)
    }
    const tq = suave(trecho(queda, (i / N) * 0.55, (i / N) * 0.55 + 0.45))
    const vaga = para >= 0 ? conta[para]++ : -1
    return { de, para, t, tq, vaga }
  })
  const contagem = Array(8).fill(0)
  estados.forEach((e) => e.tq >= 0.5 && e.para >= 0 && contagem[e.para]++)

  const ultimo = feitos > 0 ? EVENTOS[feitos - 1] : null
  const k = feitos
  const caixa = ACUM.abriu[k] - ACUM.subst[k]

  const tela = useTela(
    useCallback(
      (ctx: CanvasRenderingContext2D, cw: number, ch: number) => {
        const g = geometria(cw, ch)
        const meio = g.yRaia(0) + (g.yRaia(7) + g.raiaH - g.yRaia(0)) / 2

        // o traço chega pela esquerda e se abre nos 8 níveis
        ctx.lineWidth = 1.4
        ctx.strokeStyle = COR.oceano
        ctx.beginPath()
        ctx.moveTo(0, meio)
        ctx.lineTo(g.abre * 0.35, meio)
        ctx.stroke()
        ORDEM_FILAS.forEach((_, f) => {
          const y = g.yRaia(f) + g.raiaH / 2
          ctx.strokeStyle = corNivel(f)
          ctx.globalAlpha = 0.7
          ctx.beginPath()
          ctx.moveTo(g.abre * 0.35, meio)
          ctx.bezierCurveTo(g.abre * 0.75, meio, g.abre * 0.6, y, g.abre, y)
          ctx.lineTo(g.abre + 8, y)
          ctx.stroke()
          ctx.globalAlpha = 1
          ctx.fillStyle = foco === f ? COR.nevoa : '#ffffff'
          ctx.beginPath()
          ctx.roundRect(g.abre + 4, g.yRaia(f), cw - g.abre - 4, g.raiaH, 8)
          ctx.fill()
          ctx.fillStyle = corNivel(f)
          ctx.fillRect(g.abre + 4, g.yRaia(f) + 6, 3, g.raiaH - 12)
        })

        // chave de ordenação: dentro do nível, da data limite mais antiga para a mais nova
        if (chave > 0) {
          ctx.globalAlpha = chave
          ctx.strokeStyle = COR.oceano
          ctx.fillStyle = COR.oceano
          ctx.lineWidth = 1.2
          ORDEM_FILAS.forEach((_, f) => {
            const y = g.yRaia(f) + g.raiaH - 3
            const x1 = g.x0 + Math.min(cw - g.x0 - 12, (contagem[f] / Math.max(1, MAIOR)) * (cw - g.x0) + 20)
            ctx.beginPath()
            ctx.moveTo(g.x0, y)
            ctx.lineTo(x1, y)
            ctx.stroke()
            ctx.beginPath()
            ctx.moveTo(x1 + 5, y)
            ctx.lineTo(x1 - 1, y - 3.5)
            ctx.lineTo(x1 - 1, y + 3.5)
            ctx.fill()
          })
          ctx.globalAlpha = 1
        }

        // os pacientes
        const r = Math.max(1.1, g.pas * 0.34)
        let heroi = { x: 0, y: 0 }
        let alvo: { x: number; y: number } | null = null
        for (let i = 0; i < N; i++) {
          const pt = PONTOS[i]
          const es = estados[i]
          const a = g.naGrade(i)
          let x: number
          let y: number
          let alfa = 1
          if (es.para >= 0) {
            const b = g.naRaia(es.para, es.vaga)
            x = b.x
            y = es.t < 1 ? mix(g.yRaia(es.de) + g.raiaH / 2, b.y, suave(es.t)) : b.y
          } else {
            x = mix(cw - 30, cw - 6, es.t)
            y = g.yRaia(es.de) + g.raiaH / 2
            alfa = 1 - es.t
          }
          x = mix(a.x, x, es.tq)
          y = mix(a.y, y, es.tq)
          if (!pt.onco) alfa *= mix(1, 0.14, ouro)
          ctx.globalAlpha = alfa
          ctx.fillStyle = es.tq < 0.5 ? COR.nevoa : corNivel(es.t >= 0.5 && es.para >= 0 ? es.para : es.de)
          ctx.beginPath()
          ctx.arc(x, y, r, 0, Math.PI * 2)
          ctx.fill()
          if (pt.onco) {
            ctx.strokeStyle = COR.petroleo900
            ctx.lineWidth = 0.9
            ctx.beginPath()
            ctx.arc(x, y, r + 1.3, 0, Math.PI * 2)
            ctx.stroke()
          }
          if (i === HEROI) heroi = { x, y }
          if (ultimo && i === ultimo.paciente) alvo = { x, y }
        }
        ctx.globalAlpha = 1

        // a 621
        ctx.beginPath()
        ctx.arc(heroi.x, heroi.y, r + 5, 0, Math.PI * 2)
        ctx.strokeStyle = COR.oceano
        ctx.lineWidth = 1.4
        ctx.stroke()
        ctx.font = "600 10.5px Montserrat, system-ui, sans-serif"
        ctx.fillStyle = COR.petroleo
        ctx.textBaseline = 'middle'
        ctx.textAlign = heroi.x > cw - 50 ? 'right' : 'left'
        ctx.fillText('621', heroi.x + (heroi.x > cw - 50 ? -(r + 9) : r + 9), heroi.y - r - 6)

        if (faixa <= 0) return

        // a tira do traço: cada evento processado é uma batida
        ctx.globalAlpha = faixa
        const base = 54
        const hitX = cw * (g.fone ? 0.46 : 0.42)
        const s = mix(96, 6, Math.sqrt(rapido))
        const larg = Math.min(s * 0.72, 40)
        const grad = ctx.createLinearGradient(0, 0, hitX, 0)
        grad.addColorStop(0, 'rgba(31, 114, 124, 0.08)')
        grad.addColorStop(1, COR.oceano)
        ctx.strokeStyle = grad
        ctx.lineWidth = 1.6
        ctx.lineJoin = 'round'
        ctx.beginPath()
        ctx.moveTo(0, base)
        for (let e = Math.max(0, Math.floor(n - hitX / s - 2)); e < feitos; e++) {
          const x = hitX - (n - (e + 1)) * s
          if (x < -larg) continue
          const amp = (EVENTOS[e].acao ? 40 : 22) * mix(1, 0.75, rapido)
          for (const [u, v] of COMPLEXO) ctx.lineTo(x - larg / 2 + (u + 0.5) * larg, base + v * amp)
        }
        ctx.lineTo(hitX, base)
        ctx.stroke()

        ctx.setLineDash([3, 5])
        ctx.strokeStyle = COR.linha
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(hitX, base)
        ctx.lineTo(cw, base)
        ctx.stroke()
        ctx.setLineDash([])

        // os próximos eventos chegam pela direita
        ctx.font = "600 10.5px Montserrat, system-ui, sans-serif"
        const vao = mix(92, 56, rapido)
        for (let e = feitos; e < Math.min(NE, feitos + 5); e++) {
          const x = hitX + 18 + (e + 1 - n) * vao
          if (x > cw - 180) break
          const txt = TIPOS_EVENTO[EVENTOS[e].tipo]
          const tw = ctx.measureText(txt).width + 14
          ctx.globalAlpha = faixa * mix(1, 0.5, rapido)
          ctx.fillStyle = '#ffffff'
          ctx.strokeStyle = COR.linha
          ctx.beginPath()
          ctx.roundRect(x - 2, base - 10, tw, 20, 5)
          ctx.fill()
          ctx.stroke()
          ctx.fillStyle = COR.tinta
          ctx.fillText(txt, x + 5, base + 0.5)
        }
        ctx.globalAlpha = faixa

        // pedidos voam para a caixa do médico
        const caixaX = cw - 60
        const caixaY = 34
        const voo = mix(0.9, 30, rapido)
        for (let e = Math.max(0, Math.floor(n - voo - 1)); e < feitos; e++) {
          if (!EVENTOS[e].acao) continue
          const f = (n - (e + 1)) / voo
          if (f < 0 || f > 1) continue
          const u = 1 - f
          const cx = mix(hitX, caixaX, 0.5)
          const cy = -20
          const x = u * u * hitX + 2 * u * f * cx + f * f * caixaX
          const y = u * u * base + 2 * u * f * cy + f * f * caixaY
          ctx.fillStyle = '#ffffff'
          ctx.strokeStyle = COR.petroleo
          ctx.setLineDash(EVENTOS[e].acao === 2 ? [2, 2] : [])
          ctx.beginPath()
          ctx.roundRect(x - 9, y - 6, 18, 12, 2)
          ctx.fill()
          ctx.stroke()
          ctx.setLineDash([])
        }

        // o paciente daquele evento: o motor reavalia só ele
        if (alvo && rapido < 1) {
          const { x, y } = alvo
          ctx.globalAlpha = faixa * (1 - rapido)
          ctx.setLineDash([2, 4])
          ctx.strokeStyle = COR.oceano
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(hitX, base + 8)
          ctx.lineTo(x, y)
          ctx.stroke()
          ctx.setLineDash([])
          ctx.lineWidth = 1.6
          ctx.beginPath()
          ctx.arc(x, y, r + 6 + (n - feitos) * 8, 0, Math.PI * 2)
          ctx.stroke()
        }
        ctx.globalAlpha = faixa
        ctx.beginPath()
        ctx.arc(hitX, base, 6, 0, Math.PI * 2)
        ctx.fillStyle = COR.petroleo
        ctx.fill()
        ctx.globalAlpha = 1
      },
      [estados, n, feitos, rapido, chave, ouro, faixa, foco, ultimo, contagem],
    ),
  )

  const g = w ? geometria(w, h) : null
  const legenda =
    foco != null
      ? `${ORDEM_FILAS[foco]} · ${NOME_FILA[ORDEM_FILAS[foco]]}: ${REGRA_FILA[ORDEM_FILAS[foco]]}`
      : faixa > 0
        ? 'Nível recomendado; quem muda a fila oficial é o médico.'
        : queda < 1
          ? '902 pedidos ativos, na ordem de hoje.'
          : 'Só com o cadastro: cada pedido em um nível.'
  const deNivel = ultimo ? DE_NIVEL.get(feitos - 1) : undefined

  return (
    <section ref={ref} id="motor" className="pl-cena pl-cena-longa" data-traco="faixas" aria-labelledby="pl-motor">
      <div className="pl-palco">
        <div className="pl-vis pl-vis-alta" ref={vis}>
          <canvas
            ref={tela}
            className="pl-tela"
            role="img"
            aria-label="Os pedidos caem em oito níveis, de G1a a G7. Depois os eventos chegam um por um e movem pacientes entre níveis: G4 passa de 37 para 118."
          />

          {/* tira de cima: antes dos eventos, o que o motor lê; depois, o traço */}
          <div className="pl-tira" style={{ opacity: 1 - faixa }} aria-hidden={faixa >= 1}>
            {ouro > 0 ? (
              <p className="pl-tira-texto" style={{ opacity: ouro }}>
                <span className="pl-anel" /> CID C* · todos em G1a ou G2
              </p>
            ) : chave > 0 ? (
              <code className="pl-mono pl-tira-codigo" style={{ opacity: chave }}>
                {CHAVE}
              </code>
            ) : (
              <p className="pl-tira-texto">
                CID · dor · limitação · texto do médico <span className="text-agua">→</span> nível
              </p>
            )}
          </div>
          <div className="pl-caixa" style={{ opacity: faixa }}>
            <span>Pedidos para o médico</span>
            <b className="tabular">{br(caixa)}</b>
          </div>
          {g && (
            <div className="pl-agora" style={{ opacity: faixa }}>
              {ultimo && rapido < 1 ? (
                <>
                  <span className="text-tinta-soft">
                    evento {br(feitos)} de {br(NE)} ·
                  </span>{' '}
                  <b>{TIPOS_EVENTO[ultimo.tipo]}</b> <span>→ {DESFECHO[ultimo.acao]}</span>
                  {deNivel != null && ultimo.nivel >= 0 && (
                    <span className="ml-1 inline-flex items-center gap-1 align-middle">
                      <SeloFila f={ORDEM_FILAS[deNivel]} compacto /> → <SeloFila f={ORDEM_FILAS[ultimo.nivel]} compacto />
                    </span>
                  )}
                </>
              ) : rapido > 0 ? (
                <span className="tabular">
                  <b>{br(k)}</b> eventos · {br(ACUM.sem[k])} sem mudança · {br(ACUM.abriu[k])} pedidos abertos ·{' '}
                  {br(ACUM.evid[k])} com evidência nova
                </span>
              ) : null}
            </div>
          )}

          {g && (
            <>
              <p className="pl-legenda" style={{ top: g.topo - 26, left: g.abre + 4 }} aria-live="polite">
                {legenda}
              </p>
              <ol className="pl-raias" style={{ top: g.topo, left: g.abre + 12, bottom: g.base, rowGap: g.vao }}>
                {ORDEM_FILAS.map((cod, f) => (
                  <li
                    key={cod}
                    tabIndex={0}
                    onMouseEnter={() => setFoco(f)}
                    onMouseLeave={() => setFoco(null)}
                    onFocus={() => setFoco(f)}
                    onBlur={() => setFoco(null)}
                    aria-label={`${cod}, ${NOME_FILA[cod]}, prazo de ${PRAZO_FILA[cod]} dias, ${contagem[f]} pacientes`}
                  >
                    <span className="flex items-center gap-2" style={{ width: g.cabeca - 8 }}>
                      <SeloFila f={cod} compacto />
                      {g.cabeca > 150 && (
                        <span className="min-w-0 leading-tight">
                          <span className="block truncate text-[12px] font-semibold text-tinta">{NOME_FILA[cod]}</span>
                          <span className="tabular block text-[11px] text-tinta-soft">
                            {PRAZO_FILA[cod]} dias · <b className="text-tinta">{contagem[f]}</b>
                          </span>
                        </span>
                      )}
                      {g.cabeca > 80 && g.cabeca <= 150 && (
                        <span className="tabular text-[12px] font-semibold text-tinta">{contagem[f]}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      </div>

      <div className="pl-roteiro">
        <div className="pl-passo" data-passo>
          <div className="pl-cartao">
            <p className="pl-num">02 · Motor</p>
            <h2 id="pl-motor" className="text-[2.25rem] sm:text-[2.75rem]">Oito níveis, de G1a a G7.</h2>
            <p className="mt-3 text-[16px] text-tinta-soft">
              O motor lê o CID, a dor, a limitação e o texto do médico, e trata negação: “sem sinais de
              encarceramento” não conta como encarceramento. Cada pedido cai em um de oito níveis, baseados no SWALIS.
              A ordem entre os níveis é fixa.
            </p>
          </div>
        </div>
        <div className="pl-passo" data-passo>
          <div className="pl-cartao">
            <p className="pl-rotulo">Dentro do nível</p>
            <p className="text-[16px]">
              Vai antes quem tem a <b className="text-petroleo">data limite</b> mais antiga: entrada + prazo do nível.
              Empate: mais sinais clínicos, mais dor, entrada mais antiga.
            </p>
            <code className="pl-mono mt-4 block rounded-lg bg-nevoa-50 px-3 py-2 text-[12.5px] text-petroleo">{CHAVE}</code>
          </div>
        </div>
        <div className="pl-passo" data-passo>
          <div className="pl-cartao border-l-4 border-l-petroleo">
            <p className="pl-rotulo">Regra de ouro</p>
            <p className="font-titulo text-[1.6rem] font-bold leading-snug text-petroleo">
              Todo CID C* cai em G1a ou G2, acima de qualquer paciente sem urgência clínica.
            </p>
          </div>
        </div>
        <div className="pl-passo" data-passo data-traco="eventos" id="eventos">
          <div className="pl-cartao">
            <p className="pl-num">03 · Eventos</p>
            <h2 className="text-[2.25rem] sm:text-[2.75rem]">Eventos processados por data.</h2>
            <p className="mt-3 text-[16px] text-tinta-soft">
              Os 1.489 eventos válidos (biópsias, idas ao PS, internações, exames, ligações) são processados em ordem
              de data. Cada evento reavalia só o paciente dele. Se o nível recomendado muda, o motor abre um pedido
              para o médico.
            </p>
          </div>
        </div>
        <div className="pl-passo" data-passo>
          <div className="pl-cartao">
            <p className="tabular font-titulo text-[2.25rem] font-bold leading-tight text-petroleo">
              1.489 eventos → 128 pedidos pendentes
            </p>
            <ul className="mt-4 divide-y divide-linha border-y border-linha text-[14px]">
              <li className="py-2.5">
                <b className="tabular text-petroleo">1.225</b> não mudam o nível; atualizam só o desempate e a
                justificativa.
              </li>
              <li className="py-2.5">
                <b className="tabular text-petroleo">136</b> abrem um pedido; em 8 casos o pedido novo substitui um que
                ainda esperava decisão.
              </li>
              <li className="py-2.5">
                <b className="tabular text-petroleo">128</b> trazem evidência nova para um pedido já aberto.
              </li>
            </ul>
            <p className="mt-3 text-[14px] text-tinta-soft">
              Se todos forem aprovados, G4 · Deterioração recente vai de 37 para 118 pacientes.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
