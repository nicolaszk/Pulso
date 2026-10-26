# -*- coding: utf-8 -*-
"""
verificar_fila_priorizada.py
Verifica o entregável comum do desafio: fila_priorizada.csv (solicitacao_id, posicao, justificativa).

  1. Formato: colunas obrigatórias, posições inteiras únicas, ids existentes na fila.
  2. Cobertura: quantas solicitações da fila ficaram de fora (pode ser legítimo: duplicatas, desistências).
  3. REGRA DE OURO: nenhum paciente com CID C* abaixo de um paciente "sem urgência clínica".
     Definição conservadora de "sem urgência clínica" usada aqui:
       CID não oncológico, dor EVA <= 3, limitação nenhuma/leve, sem CID de obstrução/instabilidade,
       sem pronto-socorro/internação/biópsia positiva/progressão em imagem/reavaliação com piora nos eventos,
       e sem sinais de alarme no texto da justificativa.
  4. Indicadores informativos: posição mediana dos oncológicos, dos pacientes com piora recente etc.

Uso: python verificar_fila_priorizada.py fila_priorizada.csv [--dataset pasta_do_dataset]
"""
import argparse
import os
import sys

import pandas as pd

REF = pd.Timestamp('2026-10-23')
KW_ALARME = (r'encarcer|estrangul|colangite|icter|pancreatite|enterorragia|melena|hematemese|suboclus|perda ponderal|disfagia|sepse|'
             r'hidronefrose|perda de funcao|transfund|hemoptise|rouquidao|linfonodo.*(?:fixo|palpavel)|sangramento espontaneo|acamad|'
             r'ulcera de pressao|quedas de repeticao|glaucoma facomorfico|retencao de co2|dano neurologico|psa em elevacao|dessaturacao|'
             r'angina em repouso|sincope|crescimento rapido|retencao urinaria aguda|massa anexial|ca-125')
CID_URGENTE = {'I200', 'K403', 'K400', 'K420', 'K430', 'K800', 'N132', 'I832'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('arquivo')
    ap.add_argument('--dataset', default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()

    fila = pd.read_csv(os.path.join(a.dataset, 'fila_cirurgica.csv'))
    ev = pd.read_csv(os.path.join(a.dataset, 'eventos_clinicos.csv'), parse_dates=['data_evento'])
    out = pd.read_csv(a.arquivo)
    erros, avisos = [], []

    # 1. formato
    for c in ('solicitacao_id', 'posicao', 'justificativa'):
        if c not in out.columns: erros.append(f'coluna obrigatória ausente: {c}')
    if erros:
        print('\n'.join('ERRO: ' + e for e in erros)); sys.exit(1)
    if not out.solicitacao_id.is_unique: erros.append('solicitacao_id repetido no arquivo')
    if not pd.api.types.is_integer_dtype(out.posicao): erros.append('posicao deve ser inteira')
    elif not out.posicao.is_unique: erros.append('posicao repetida')
    desconhecidos = set(out.solicitacao_id) - set(fila.solicitacao_id)
    if desconhecidos: erros.append(f'{len(desconhecidos)} solicitacao_id não existem na fila (ex.: {sorted(desconhecidos)[:3]})')
    vazias = out.justificativa.isna() | (out.justificativa.astype(str).str.strip() == '')
    if vazias.any(): avisos.append(f'{int(vazias.sum())} linhas sem justificativa')

    # 2. cobertura
    fora = set(fila.solicitacao_id) - set(out.solicitacao_id)
    if fora: avisos.append(f'{len(fora)} solicitações da fila não aparecem no arquivo (ok se forem duplicatas/desistências explicadas no DECISOES.md)')

    # 3. regra de ouro
    f = fila.set_index('solicitacao_id')
    f['cid'] = f.cid_principal.str.upper().str.replace('.', '', regex=False)
    f['onco'] = f.cid.str.startswith('C')
    piora_ids = set(ev[ev.tipo_evento.isin(['pronto_socorro', 'internacao'])
                       | ((ev.tipo_evento == 'biopsia') & (ev.resultado == 'positivo'))
                       | ((ev.tipo_evento == 'exame_imagem') & (ev.resultado == 'progressao'))
                       | ((ev.tipo_evento == 'consulta_reavaliacao') & (ev.resultado == 'piora'))].solicitacao_id)
    txt = f.justificativa_clinica.fillna('').str.lower().str.contains(KW_ALARME, regex=True)
    f['sem_urgencia'] = ((~f.onco) & (f.intensidade_dor_eva.fillna(0) <= 3) & f.limitacao_funcional.fillna('nenhuma').isin(['nenhuma', 'leve'])
                         & ~f.cid.isin(CID_URGENTE) & ~f.index.isin(piora_ids) & ~txt)
    o = out.sort_values('posicao').set_index('solicitacao_id')
    o = o.join(f[['onco', 'sem_urgencia', 'cid_principal']], how='left')
    if o.sem_urgencia.fillna(False).any():
        primeiro_calmo = o[o.sem_urgencia.fillna(False)].posicao.min()
        viol = o[o.onco.fillna(False) & (o.posicao > primeiro_calmo)]
        if len(viol):
            erros.append(f'REGRA DE OURO VIOLADA: {len(viol)} paciente(s) oncológico(s) abaixo do primeiro paciente sem urgência clínica '
                         f'(posição {primeiro_calmo}). Exemplos: {", ".join(f"{i} ({r.cid_principal}, pos {r.posicao})" for i, r in viol.head(5).iterrows())}')
    onco_fora = [s for s in f[f.onco].index if s in fora]
    if onco_fora: avisos.append(f'{len(onco_fora)} oncológicos ficaram FORA do arquivo — justifique no DECISOES.md (ex.: {onco_fora[:3]})')

    # 4. indicadores
    n = len(o)
    print(f'Arquivo: {a.arquivo}  |  {n} posições  |  fila: {len(fila)} solicitações')
    print(f'- posição mediana dos oncológicos: {o[o.onco.fillna(False)].posicao.median():.0f} de {n}')
    print(f'- oncológicos no primeiro terço: {(o[o.onco.fillna(False)].posicao <= n / 3).mean():.0%}')
    rec = set(ev[(ev.data_evento >= REF - pd.Timedelta(days=180)) & ev.tipo_evento.isin(['pronto_socorro', 'internacao'])].solicitacao_id)
    pr = o[o.index.isin(rec)]
    if len(pr): print(f'- pacientes com PS/internação nos últimos 180 dias na primeira metade: {(pr.posicao <= n / 2).mean():.0%}')
    calmos = o[o.sem_urgencia.fillna(False)]
    if len(calmos): print(f'- pacientes sem urgência clínica no último terço: {(calmos.posicao > 2 * n / 3).mean():.0%}')
    print()
    for w in avisos: print('AVISO:', w)
    for e in erros: print('ERRO: ', e)
    print('\nRESULTADO:', 'OK — regra de ouro respeitada e formato válido' if not erros else f'{len(erros)} erro(s)')
    sys.exit(1 if erros else 0)


if __name__ == '__main__':
    main()
