"""Cliente LLM: qualquer provedor com a API de chat da OpenAI.

  PULSO_LLM_PROVIDER  ollama (padrao, local) | groq | gemini | openrouter
  PULSO_LLM_MODEL     modelo do provedor (padrao na tabela abaixo)
  PULSO_LLM_URL       endereco da API (no docker compose: o Ollama da maquina, via host.docker.internal)
  GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY para os hospedados (backend/.env ou .env da raiz)

Ollama local: `OLLAMA_NUM_PARALLEL=4 ollama serve` e `ollama pull gemma4:e4b` (4B efetivos, ~5 s por texto;
gemma4:e2b e o mais rapido, ~3 s, e erra mais: a conferencia recusa e ele tenta de novo).
"""
from __future__ import annotations

import json
import os
import re
import time

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from . import config  # noqa: F401  (carrega os .env)

PROVEDORES = {
    "ollama": ("http://localhost:11434/v1", None, "gemma4:e4b"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-20b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "gemini-2.5-flash"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "qwen/qwen3-14b:free"),
}
# Raciocinio desligado ou curto: o texto e curto e pensar so deixa mais lento
RACIOCINIO = {"ollama": "none", "groq": "low"}


class LLMIndisponivel(Exception):
    """Provedor fora do ar, sem chave, limite de uso ou resposta sem JSON."""


class LLM:
    def __init__(self, provedor: str | None = None, modelo: str | None = None, timeout: float = 120):
        self.provedor = provedor or os.getenv("PULSO_LLM_PROVIDER", "ollama")
        if self.provedor not in PROVEDORES:
            raise LLMIndisponivel(f"provedor desconhecido: {self.provedor}")
        base_url, chave_env, modelo_padrao = PROVEDORES[self.provedor]
        base_url = os.getenv("PULSO_LLM_URL", base_url)
        chave = os.getenv(chave_env) if chave_env else "ollama"
        if not chave:
            raise LLMIndisponivel(f"defina {chave_env} para usar {self.provedor}")
        self.modelo = modelo or os.getenv("PULSO_LLM_MODEL", modelo_padrao)
        self.raciocinio = os.getenv("PULSO_LLM_REASONING", RACIOCINIO.get(self.provedor, ""))
        self.cliente = OpenAI(base_url=base_url, api_key=chave, timeout=timeout, max_retries=1)

    def json(self, sistema: str, usuario: str) -> tuple[dict, float]:
        """Pede um objeto JSON (temperatura 0). Devolve (objeto, segundos)."""
        mensagens = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
        extra = {"reasoning_effort": self.raciocinio} if self.raciocinio else {}
        t0 = time.time()
        for formato in ({"type": "json_object"}, None):  # nem todo provedor aceita response_format
            try:
                resp = self.cliente.chat.completions.create(
                    model=self.modelo, messages=mensagens, temperature=0,
                    **extra, **({"response_format": formato} if formato else {}))
                break
            except (APIConnectionError, APITimeoutError) as exc:
                raise LLMIndisponivel(f"{self.provedor} fora do ar: {exc}") from exc
            except APIStatusError as exc:
                if exc.status_code in (401, 403, 404, 429) or formato is None:
                    raise LLMIndisponivel(f"{self.provedor} respondeu {exc.status_code}: {exc.message}") from exc
        bruto = re.sub(r"<think>.*?</think>", "", resp.choices[0].message.content or "", flags=re.S)
        m = re.search(r"\{.*\}", bruto, flags=re.S)
        try:
            return json.loads(m.group(0)), round(time.time() - t0, 1)
        except (AttributeError, json.JSONDecodeError) as exc:
            raise LLMIndisponivel(f"resposta sem JSON: {bruto[:200]}") from exc
