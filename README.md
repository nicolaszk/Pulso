# Pulso

Priorização da fila de cirurgias eletivas. Projeto da 9ª Hackatona de Engenharia de Software 2026 (Fin-x, PUCRS, Hospital São Lucas), Desafio 1: Priorização Inteligente da Fila Cirúrgica.

Desenvolvemos um motor de regras determinístico baseado em filas de prioridade: cada paciente cai num nível de urgência, e a cada evento clínico novo (ida ao PS, internação, laudo, biópsia) o motor reavalia esse paciente e, se for o caso, propõe que ele mude de nível. Quem decide é o médico regulador, que aprova ou rejeita cada proposta; a fila oficial só muda com o aval dele. Usamos um LLM local apenas para reescrever, em linguagem clara, os fatos que o motor já calculou, sem que ele interfira na ordem da fila.

**Regra de ouro:** nenhum paciente com CID `C*` fica abaixo de um paciente sem urgência clínica. Ela vale por construção no motor e é conferida de novo no banco a cada aprovação.

<!-- prints da aplicação aqui -->

## Como funciona

1. **Limpeza:** os CSVs do desafio são normalizados, duplicatas fundidas e eventos inválidos vão para a quarentena. Nada é apagado.
2. **Motor:** cada solicitação cai num de 8 níveis (G1a a G7, adaptados do SWALIS), cada um com um prazo. Dentro do nível, quem está mais atrasado vem primeiro.
3. **Eventos:** os eventos clínicos são processados um a um, por data. Se o motor quer outro nível, abre um pedido para o médico.
4. **Decisão humana:** o médico aprova ou rejeita (com motivo) na Revisão humana. Só então a fila oficial muda.
5. **Explicação em linguagem clara:** um LLM local (gemma4:e4b via Ollama) reescreve os fatos do motor em 2 ou 3 frases. Uma conferência determinística recusa qualquer número, data, nível ou termo oncológico que não esteja nos fatos; se falhar, vale a justificativa do motor. O LLM nunca muda a fila.
6. **Máquina do Tempo:** replay do log de eventos que mede quantos pacientes o motor teria promovido durante a espera, comparado à prioridade manual.

| Nível | Critério | Prazo |
|---|---|---|
| G1a | Oncológico em progressão | 15 d |
| G1b | Agudo não oncológico | 15 d |
| G2 | Oncológico confirmado | 21 d |
| G3 | Suspeita oncológica | 60 d |
| G4 | Deterioração recente | 60 d |
| G5 | Alta carga de sintomas | 60 d |
| G6 | Sintomático moderado | 180 d |
| G7 | Eletivo estável | 360 d |

## Estrutura

| Pasta | O que tem |
|---|---|
| [`backend/`](backend/README.md) | Motor de priorização, pipeline de eventos, PostgreSQL, API (FastAPI) e explicações por LLM |
| [`frontend/`](frontend/README.md) | SPA em React: área pública (paciente), área profissional (médico regulador) e a página `/pipeline` |

Decisões de projeto e documentação técnica completa: [`backend/DECISOES.md`](backend/DECISOES.md). Fila entregue e resultado do verificador oficial: [`backend/resultados/`](backend/resultados/README.md).

## Rodar

Precisa de Docker e Node.

**Backend** (banco + carga do dataset + API em `http://localhost:8000/docs`):

```bash
cd backend
docker compose up -d --build
```

A primeira subida leva cerca de um minuto. Para deixar a caixa do médico no estado da demo (3 pedidos, o resto dos eventos pendente):

```bash
docker compose exec api python -m src.pipeline carregar --recriar --ate-pedidos 3
```

**Frontend** (em `http://localhost:5173`):

```bash
cd frontend
npm install
npm run dev
```

**Entrar como médico:** um CRM de `GET /medicos` (ex.: `CRM-RS 900001`) e qualquer senha com 4+ caracteres.

**Consulta pública:** use um dos pacientes de exemplo, ex.: CPF `529.982.247-25`, nascimento `14/03/1974` (lista completa no [README do frontend](frontend/README.md#área-pública)).

**LLM (opcional):** as explicações do dataset já vêm versionadas em `backend/db/explicacoes.jsonl`, então a demo roda sem LLM. Para a API gerar textos novos na hora, rode o Ollama na sua máquina (o container da API já aponta para ele):

```bash
ollama pull gemma4:e4b
OLLAMA_NUM_PARALLEL=4 ollama serve
```

Sem o Ollama, vale a justificativa do motor. Provedores hospedados (Groq, Gemini, OpenRouter) são opcionais via `PULSO_LLM_PROVIDER`; detalhes no [README do backend](backend/README.md#explicações-em-linguagem-clara-llm-opcional).

## Stack

Python 3.12, pandas, FastAPI, PostgreSQL 16, Docker Compose, Ollama (gemma4:e4b) · React 19, React Router, Tailwind CSS 4, Vite, TypeScript.
