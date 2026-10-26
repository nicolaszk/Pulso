import { useRef } from 'react'
import { Traco } from './pipeline/Traco'
import { Abertura } from './pipeline/secoes/Abertura'
import { Limpeza } from './pipeline/secoes/Limpeza'
import { Motor } from './pipeline/secoes/Motor'
import { Medico } from './pipeline/secoes/Medico'
import { MaquinaTempo } from './pipeline/secoes/MaquinaTempo'
import { Saida } from './pipeline/secoes/Saida'
import './pipeline/pipeline.css'

/**
 * O pipeline por dentro, em rolagem: entrada e limpeza, motor em 8 níveis, eventos um por um,
 * decisão do médico e a fila com recibos. Feito para ser explicado em uns 2 minutos e meio.
 */
export function Pipeline() {
  const papel = useRef<HTMLDivElement>(null)
  return (
    <div className="pipeline">
      <Abertura />
      <div className="relative" ref={papel}>
        <Traco papel={papel} />
        <Limpeza />
        <Motor />
        <Medico />
        <MaquinaTempo />
        <Saida />
      </div>
    </div>
  )
}
