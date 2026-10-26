"""Gera db/seed.sql a partir dos CSVs de ideas/data/dataset/.

Uso: python db/gerar_seed.py [--dataset ideas/data/dataset] [--saida db/seed.sql]

Só usa a biblioteca padrão. O resultado é determinístico (semente fixa), então o
seed.sql pode ser versionado e recarregado em qualquer máquina com:
    psql -d pulso -f db/schema.sql -f db/seed.sql

O que o script faz além de copiar os CSVs:
  - normaliza CID (maiúsculas, sem ponto), prioridade (minúsculas, sem acento)
    e município (grafia mais comum entre as variações de caixa);
  - marca duplicatas (mesmo paciente + procedimento): fica ativa a mais antiga;
  - marca saídas (desistência ou cirurgia em outro serviço, por evento ou observação);
  - descarta eventos órfãos e eventos duplicados exatos (listados no seed.sql);
  - gera 3 hospitais e 2 médicos por especialidade, que não existem no dataset.
"""
import argparse
import csv
import os
import random
import re
import unicodedata
from collections import Counter, defaultdict

SEMENTE = 42

HOSPITAIS = [
    # (nome, município). O primeiro recebe todas as solicitações: a distância do
    # dataset é até um único hospital. Os outros dois são sintéticos.
    ('Hospital Sao Lucas', 'Porto Alegre'),
    ('Hospital Regional Sul', 'Pelotas'),
    ('Hospital Regional Serra', 'Caxias do Sul'),
]
MEDICOS_POR_ESPECIALIDADE = 2

PRENOMES = ['Ana', 'Bruno', 'Carla', 'Daniel', 'Eduarda', 'Felipe', 'Gabriela', 'Henrique',
            'Isabela', 'Joao', 'Larissa', 'Marcelo', 'Natalia', 'Otavio', 'Patricia', 'Rafael',
            'Simone', 'Tiago', 'Vanessa', 'Vitor', 'Juliana', 'Leonardo', 'Mariana', 'Rodrigo']
SOBRENOMES = ['Almeida', 'Barbosa', 'Castro', 'Dias', 'Esteves', 'Farias', 'Goulart', 'Hoffmann',
              'Klein', 'Lemos', 'Moreira', 'Nunes', 'Oliveira', 'Prates', 'Ramos', 'Sartori',
              'Teixeira', 'Vieira', 'Zanini', 'Becker']

# Saída da fila escrita em observacoes (o evento de contato nem sempre existe)
SAIDA_OBS = re.compile(r'desistiu|operou pelo convenio|realizou a cirurgia em outro', re.I)
SAIDA_EVENTO = {'desistiu', 'informou_cirurgia_outro_servico'}


def sem_acento(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c))


def cid(valor):
    return valor.strip().upper().replace('.', '') or None


def ler(caminho):
    with open(caminho, encoding='utf-8', newline='') as arq:
        return list(csv.DictReader(arq))


def sql(valor):
    """Literal SQL: None vira NULL, bool vira true/false, listas viram text[]."""
    if valor is None:
        return 'NULL'
    if isinstance(valor, bool):
        return 'true' if valor else 'false'
    if isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, list):
        return "'{" + ','.join('"' + v.replace('"', '\\"') + '"' for v in valor) + "}'"
    return "'" + str(valor).replace("'", "''") + "'"


def vazio(valor):
    valor = valor.strip()
    return valor or None


def inteiro(valor):
    valor = valor.strip()
    return int(valor) if valor else None


def decimal(valor):
    valor = valor.strip()
    return float(valor) if valor else None


def insert(tabela, colunas, linhas):
    if not linhas:
        return ''
    cabecalho = f'INSERT INTO {tabela} ({", ".join(colunas)}) VALUES\n'
    corpo = ',\n'.join('  (' + ', '.join(sql(v) for v in linha) + ')' for linha in linhas)
    return cabecalho + corpo + ';\n\n'


def gerar_medicos(especialidades, esp_id, rng):
    """2 médicos sintéticos por especialidade. Também usado pela carga do backend
    (backend/src/pipeline/carga.py), para os dois gerarem os mesmos médicos."""
    medicos = []
    nomes_usados = set()
    medicos_por_esp = defaultdict(list)
    for nome_esp in especialidades:
        for i in range(MEDICOS_POR_ESPECIALIDADE):
            while True:
                nome = f'{rng.choice(PRENOMES)} {rng.choice(SOBRENOMES)}'
                if nome not in nomes_usados:
                    nomes_usados.add(nome)
                    break
            medico_id = len(medicos) + 1
            hospital_id = 1 if i == 0 else 2 + (esp_id[nome_esp] % (len(HOSPITAIS) - 1))
            medicos.append((nome, f'CRM-RS {900000 + medico_id}', esp_id[nome_esp], hospital_id))
            medicos_por_esp[esp_id[nome_esp]].append(medico_id)
    return medicos, medicos_por_esp


def main():
    ap = argparse.ArgumentParser()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--dataset', default=os.path.join(raiz, 'ideas', 'data', 'dataset'))
    ap.add_argument('--saida', default=os.path.join(raiz, 'db', 'seed.sql'))
    args = ap.parse_args()

    rng = random.Random(SEMENTE)
    fila = ler(os.path.join(args.dataset, 'fila_cirurgica.csv'))
    eventos = ler(os.path.join(args.dataset, 'eventos_clinicos.csv'))
    procs = ler(os.path.join(args.dataset, 'procedimentos.csv'))
    swalis = ler(os.path.join(args.dataset, 'referencias', 'swalis.csv'))

    # Especialidades e procedimentos ------------------------------------------
    especialidades = sorted({p['especialidade'] for p in procs})
    esp_id = {nome: i for i, nome in enumerate(especialidades, start=1)}
    proc_esp = {p['procedimento_id']: esp_id[p['especialidade']] for p in procs}

    # Hospitais e médicos (sintéticos) ------------------------------------------
    medicos, medicos_por_esp = gerar_medicos(especialidades, esp_id, rng)

    # Normalização de município: a grafia mais comum entre as variações de caixa
    grafias = defaultdict(Counter)
    for linha in fila:
        grafias[sem_acento(linha['municipio'].strip().lower())][linha['municipio'].strip()] += 1
    municipio = {chave: cont.most_common(1)[0][0] for chave, cont in grafias.items()}

    # Pacientes: atributos do paciente vêm da solicitação mais antiga
    fila.sort(key=lambda l: (l['data_entrada_fila'], l['solicitacao_id']))
    pacientes = {}
    for linha in fila:
        pid = linha['paciente_id']
        nome = linha['nome_paciente'].strip()
        if pid in pacientes:
            # Prefere a grafia que não está toda em maiúsculas
            if pacientes[pid]['nome'].isupper() and not nome.isupper():
                pacientes[pid]['nome'] = nome
            continue
        comorb = [c.strip() for c in linha['comorbidades'].split(';') if c.strip()]
        pacientes[pid] = {
            'nome': nome,
            'sexo': linha['sexo'],
            'idade': int(linha['idade']),
            'municipio': municipio[sem_acento(linha['municipio'].strip().lower())],
            'uf': linha['uf'],
            'distancia': inteiro(linha['distancia_hospital_km']),
            'comorbidades': [] if comorb == ['nenhuma'] else comorb,
        }

    # Eventos: órfãos e duplicados exatos ficam de fora --------------------------
    ids_fila = {l['solicitacao_id'] for l in fila}
    orfaos, duplicados, vistos, eventos_ok = [], [], {}, []
    for ev in eventos:
        if ev['solicitacao_id'] not in ids_fila:
            orfaos.append(ev['evento_id'])
            continue
        chave = tuple(ev[c] for c in ('solicitacao_id', 'data_evento', 'tipo_evento', 'resultado',
                                      'valor_numerico', 'descricao', 'origem'))
        if chave in vistos:
            duplicados.append((ev['evento_id'], vistos[chave]))
            continue
        vistos[chave] = ev['evento_id']
        eventos_ok.append(ev)

    # Status: duplicatas primeiro, depois saídas ---------------------------------
    status = {}
    primeira = {}
    for linha in fila:  # já ordenada por data de entrada
        chave = (linha['paciente_id'], linha['procedimento_id'])
        if chave in primeira:
            status[linha['solicitacao_id']] = ('duplicata', primeira[chave],
                                               'mesmo paciente e procedimento de ' + primeira[chave])
        else:
            primeira[chave] = linha['solicitacao_id']

    saida_evento = {}
    for ev in eventos_ok:
        if ev['tipo_evento'] == 'contato_telefonico' and ev['resultado'] in SAIDA_EVENTO:
            saida_evento.setdefault(ev['solicitacao_id'], ev)
    for linha in fila:
        sid = linha['solicitacao_id']
        if sid in status:
            continue
        ev = saida_evento.get(sid)
        if ev:
            status[sid] = ('saiu', None, f"{ev['resultado']} em {ev['data_evento']} ({ev['evento_id']})")
        elif SAIDA_OBS.search(linha['observacoes']):
            status[sid] = ('saiu', None, 'observacao: ' + linha['observacoes'].strip())

    # Solicitações --------------------------------------------------------------
    solicitacoes = []
    for linha in fila:
        sid = linha['solicitacao_id']
        st, dup_de, motivo = status.get(sid, ('ativa', None, None))
        prio = sem_acento(linha['prioridade_regulacao'].strip().lower()) or None
        solicitacoes.append([
            sid, linha['paciente_id'], linha['procedimento_id'], 1,
            rng.choice(medicos_por_esp[proc_esp[linha['procedimento_id']]]),
            cid(linha['cid_principal']), linha['cid_descricao'].strip(), cid(linha['cid_secundario']),
            inteiro(linha['asa']), inteiro(linha['intensidade_dor_eva']), vazio(linha['limitacao_funcional']),
            linha['justificativa_clinica'].strip(), vazio(linha['observacoes']),
            linha['data_entrada_fila'], prio, linha['data_ultima_revisao_prioridade'],
            decimal(linha['hba1c_ultima']), vazio(linha['data_hba1c_ultima']),
            linha['avaliacao_pre_anestesica'], linha['exames_pre_op_validos'] == 'sim',
            st, dup_de, motivo,
        ])
    # Duplicata referencia a solicitação mantida: inserir as mantidas primeiro
    solicitacoes.sort(key=lambda s: s[20] == 'duplicata')

    # Escrita -------------------------------------------------------------------
    contagem = Counter(s[20] for s in solicitacoes)
    with open(args.saida, 'w', encoding='utf-8') as out:
        out.write('-- Gerado por db/gerar_seed.py a partir de ideas/data/dataset/. Não editar à mão.\n')
        out.write(f'-- Solicitações: {len(solicitacoes)} ({dict(sorted(contagem.items()))})\n')
        out.write(f'-- Eventos carregados: {len(eventos_ok)} de {len(eventos)}\n')
        out.write(f'-- Eventos órfãos descartados ({len(orfaos)}): {", ".join(orfaos)}\n')
        out.write(f'-- Eventos duplicados descartados ({len(duplicados)}): '
                  + ', '.join(f'{d} (igual a {o})' for d, o in duplicados) + '\n')
        out.write('-- Hospitais e médicos são sintéticos (não existem no dataset).\n\n')
        out.write('BEGIN;\n\n')
        out.write('INSERT INTO especialidade (id, nome) OVERRIDING SYSTEM VALUE VALUES\n'
                  + ',\n'.join(f'  ({i}, {sql(n)})' for n, i in esp_id.items()) + ';\n\n')
        out.write('INSERT INTO hospital (id, nome, municipio) OVERRIDING SYSTEM VALUE VALUES\n'
                  + ',\n'.join(f'  ({i}, {sql(n)}, {sql(m)})' for i, (n, m) in enumerate(HOSPITAIS, start=1))
                  + ';\n\n')
        out.write('INSERT INTO medico (id, nome, crm, especialidade_id, hospital_id) OVERRIDING SYSTEM VALUE VALUES\n'
                  + ',\n'.join(f'  ({i}, {sql(n)}, {sql(c)}, {e}, {h})'
                               for i, (n, c, e, h) in enumerate(medicos, start=1)) + ';\n\n')
        out.write(insert('procedimento',
                         ['id', 'nome', 'especialidade_id', 'porte', 'risco_cirurgico', 'duracao_media_min',
                          'necessita_uti'],
                         [[p['procedimento_id'], p['procedimento'], esp_id[p['especialidade']], p['porte'],
                           int(p['risco_cirurgico']), int(p['duracao_media_min']), p['necessita_uti']]
                          for p in procs]))
        out.write(insert('swalis_classe', ['classe', 'descricao', 'prazo_maximo_dias', 'exemplos'],
                         [[s['classe'], s['descricao'], int(s['prazo_maximo_dias']), s['exemplos']]
                          for s in swalis]))
        out.write(insert('paciente',
                         ['id', 'nome', 'sexo', 'idade', 'municipio', 'uf', 'distancia_hospital_km',
                          'comorbidades'],
                         [[pid, p['nome'], p['sexo'], p['idade'], p['municipio'], p['uf'], p['distancia'],
                           p['comorbidades']] for pid, p in sorted(pacientes.items())]))
        out.write(insert('solicitacao',
                         ['id', 'paciente_id', 'procedimento_id', 'hospital_id', 'medico_solicitante_id',
                          'cid_principal', 'cid_descricao', 'cid_secundario', 'asa', 'intensidade_dor_eva',
                          'limitacao_funcional', 'justificativa_clinica', 'observacoes', 'data_entrada_fila',
                          'prioridade_regulacao', 'data_ultima_revisao_prioridade', 'hba1c_ultima',
                          'data_hba1c_ultima', 'avaliacao_pre_anestesica', 'exames_pre_op_validos',
                          'status', 'duplicata_de', 'motivo_status'],
                         solicitacoes))
        out.write(insert('evento_clinico',
                         ['id', 'solicitacao_id', 'data_evento', 'tipo_evento', 'resultado', 'valor_numerico',
                          'descricao', 'origem'],
                         [[ev['evento_id'], ev['solicitacao_id'], ev['data_evento'], ev['tipo_evento'],
                           ev['resultado'], decimal(ev['valor_numerico']), ev['descricao'], ev['origem']]
                          for ev in eventos_ok]))
        # Ordem de hoje, descrita no case: prioridade manual e, dentro dela, data de entrada
        out.write('-- posicao_inicial = método atual: prioridade manual (alta, media, baixa, vazia),\n'
                  '-- depois data de entrada. posicao_final e justificativa ficam para o motor.\n'
                  'INSERT INTO fila_priorizada (solicitacao_id, posicao_inicial)\n'
                  'SELECT id, row_number() OVER (\n'
                  "           ORDER BY CASE prioridade_regulacao WHEN 'alta' THEN 1 WHEN 'media' THEN 2\n"
                  "                                              WHEN 'baixa' THEN 3 ELSE 4 END,\n"
                  '                    data_entrada_fila, id)\n'
                  "FROM solicitacao WHERE status = 'ativa';\n\n")
        out.write('COMMIT;\n')

    print(f'{args.saida}: {len(solicitacoes)} solicitações {dict(contagem)}, {len(pacientes)} pacientes, '
          f'{len(eventos_ok)} eventos, {len(orfaos)} órfãos e {len(duplicados)} duplicados descartados, '
          f'{len(HOSPITAIS)} hospitais, {len(medicos)} médicos')


if __name__ == '__main__':
    main()
