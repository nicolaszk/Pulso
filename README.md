# Pulso — Frontend

Plataforma de regulação da fila de cirurgias eletivas. Duas áreas separadas:

- **Pública** (`/`, `/como-funciona`): o paciente consulta só o próprio encaminhamento com CPF ou Cartão Nacional de Saúde e data de nascimento.
- **Profissional** (`/profissional/*`): médicos reguladores acessam Visão geral, Fila, Revisão humana e a tela de cada paciente, lendo e decidindo direto na API do [Pulso-Backend](../Pulso-Backend).

E a página **Pipeline** (`/pipeline`), que mostra em rolagem como a fila é montada (entrada e limpeza, motor, decisão do médico, máquina do tempo e saída). Ela tem link no menu da área profissional e no fim de "Como funciona".

## Rodar

1. Suba o backend (repositório `Pulso-Backend`, branch `main`): banco, carga e API em `http://localhost:8000`. O passo a passo está no README de lá. Para a demo, carregue assim:

   ```bash
   python -m src.pipeline carregar --recriar --ate-pedidos 3
   ```

   A Revisão humana começa com 3 pedidos e o restante dos eventos fica pendente para o botão **Processar próximo evento**.

2. No front:

   ```bash
   npm install
   npm run dev
   ```

Abre em `http://localhost:5173`. O backend libera essa porta por padrão: se o Vite subir em outra (porta ocupada), libere a 5173 ou ajuste `PULSO_CORS` no backend. Para apontar para outra API, copie `.env.example` para `.env` e ajuste `VITE_API_URL`.

**Entrada profissional:** use o CRM de um médico cadastrado no backend (ex.: `CRM-RS 900001`, lista em `GET /medicos`) e qualquer senha com 4+ caracteres. O backend ainda não tem autenticação; o CRM identifica quem decide.

## Stack

React 19, React Router, Tailwind CSS 4, Vite, TypeScript.

## Integração com a API

`src/api/` — cliente (`cliente.ts`), tipos das respostas (`tipos.ts`), hook de carregamento (`useApi.ts`) e rótulos dos códigos do motor (`rotulos.ts`).

| Tela | Endpoints |
| --- | --- |
| Visão geral | `GET /resumo`, `GET /marcacoes?severidade=alta` |
| Fila | `GET /fila?modo=oficial` |
| Paciente | `GET /solicitacoes/{id}`, `GET /solicitacoes/{id}/explicacao?gerar=false` |
| Revisão humana | `GET /mudancas?com_explicacao=true`, `POST /mudancas/{id}/decisao`, `POST /eventos/processar` |
| Entrada | `GET /medicos` |

A fila oficial só muda quando o médico aprova um pedido na Revisão humana; a regra de ouro é conferida pelo backend a cada aprovação.

**Explicações em linguagem clara:** a Revisão humana e o Paciente mostram o texto gerado pelo LLM do backend quando ele já existe (o front não gera na hora). Sem texto pronto, aparece o motivo técnico do motor. Para gerar os textos dos pedidos pendentes, veja "Plain-language explanations" no README do backend.

## Níveis da fila

| Nível | Nome | Prazo |
| --- | --- | --- |
| G1a | Oncológico em progressão | 15 d |
| G1b | Agudo não oncológico | 15 d |
| G2 | Oncológico confirmado | 21 d |
| G3 | Suspeita oncológica | 60 d |
| G4 | Deterioração recente | 60 d |
| G5 | Alta carga de sintomas | 60 d |
| G6 | Sintomático moderado | 180 d |
| G7 | Eletivo estável | 360 d |

## Área pública

O dataset não tem CPF nem data de nascimento, então a consulta pública usa dados locais (`src/data/`, `src/store/`), inclusive o nível e a posição na fila mostrados ao paciente. Pacientes para testar:

| Paciente | CPF | Nascimento |
| --- | --- | --- |
| Maria Oliveira | `529.982.247-25` | `14/03/1974` |
| Antônio Ferreira | `204.331.578-10` | `30/09/1951` |
| Lúcia Fernandes | `227.390.416-91` | `30/05/1965` |
| Helena Duarte | `318.204.557-18` | `11/02/1968` |

## Página Pipeline

`src/pages/publico/Pipeline.tsx` e `src/pages/publico/pipeline/`. Não chama a API: usa os JSON em `src/pages/publico/pipeline/dados/`, gerados a partir do código real do backend (instruções de uso no topo de cada script):

| Script | Gera | Precisa |
| --- | --- | --- |
| `scripts/dados_historia.py` | `fila.json`, `recibos.json` (seções de limpeza, motor, médico e saída) | Postgres do backend no ar |
| `scripts/dados_maquina_tempo.py` | `maquina_tempo.json` (seção Máquina do tempo) | Só o módulo `fila_cirurgica` do backend |
