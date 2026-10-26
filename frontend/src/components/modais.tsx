import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/cliente'
import { motivoSemPrefixo } from '../api/rotulos'
import type { Mudanca, ResultadoDecisao } from '../api/tipos'
import { AreaTexto, Botao, Modal, SeloFila } from './ui'

const MINIMO = 15

export type Decisao = 'aprovar' | 'rejeitar'

export function rotulosDecisao(m: Mudanca) {
  return m.tipo === 'sair'
    ? { aprovar: 'Confirmar saída', rejeitar: 'Manter na fila' }
    : { aprovar: 'Confirmar alteração', rejeitar: 'Manter nível atual' }
}

/** Registra a decisão do médico no backend (POST /mudancas/{id}/decisao). */
export function ModalDecisao({
  mudanca,
  decisao,
  medicoId,
  aoFechar,
  aoDecidir,
}: {
  mudanca: Mudanca | null
  decisao: Decisao
  medicoId: number
  aoFechar: () => void
  aoDecidir: (m: Mudanca, r: ResultadoDecisao) => void
}) {
  const [texto, setTexto] = useState('')
  const [tentou, setTentou] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [falha, setFalha] = useState<string | null>(null)

  useEffect(() => {
    setTexto('')
    setTentou(false)
    setFalha(null)
  }, [mudanca, decisao])

  const erro = texto.trim().length < MINIMO ? `Mínimo de ${MINIMO} caracteres.` : undefined

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setTentou(true)
    if (erro || !mudanca) return
    setEnviando(true)
    setFalha(null)
    try {
      const r = await api.decidir(mudanca.id, { decisao, medico_id: medicoId, motivo: texto.trim() })
      aoDecidir(mudanca, r)
      aoFechar()
    } catch (e) {
      setFalha(e instanceof Error ? e.message : 'Não foi possível registrar a decisão.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal
      aberto={!!mudanca}
      aoFechar={aoFechar}
      titulo={mudanca ? rotulosDecisao(mudanca)[decisao] : ''}
      subtitulo={mudanca && `${mudanca.paciente_nome} · ${mudanca.procedimento}`}
    >
      {mudanca && (
        <form onSubmit={enviar} noValidate>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <SeloFila f={mudanca.fila_atual} nome />
            {decisao === 'aprovar' && (
              <>
                <span aria-hidden="true">→</span>
                {mudanca.fila_proposta ? (
                  <SeloFila f={mudanca.fila_proposta} nome />
                ) : (
                  <span className="text-sm font-semibold">sai da fila</span>
                )}
              </>
            )}
          </div>
          <p className="rounded-lg bg-nevoa-50 px-4 py-3 text-sm">{motivoSemPrefixo(mudanca.motivo)}</p>
          <div className="mt-5">
            <AreaTexto rotulo="Justificativa" erro={tentou ? erro : undefined} valor={texto} aoMudar={setTexto} minimo={MINIMO} />
          </div>
          {falha && (
            <p role="alert" className="mt-4 rounded-lg bg-urgente-50 px-3.5 py-2.5 text-sm font-medium text-urgente">
              {falha}
            </p>
          )}
          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Botao type="button" variante="secundario" onClick={aoFechar}>
              Cancelar
            </Botao>
            <Botao type="submit" carregando={enviando}>
              Registrar decisão
            </Botao>
          </div>
        </form>
      )}
    </Modal>
  )
}
