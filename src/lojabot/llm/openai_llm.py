"""Adaptador para a API da OpenAI (Chat Completions com function calling)."""
from __future__ import annotations

import json

from lojabot.ferramentas import Ferramenta
from lojabot.llm.base import Chamada, RespostaLLM


class ProvedorOpenAI:
    def __init__(self, api_key: str, modelo: str, max_tokens: int = 800):
        import openai

        self.cliente = openai.OpenAI(api_key=api_key)
        self.modelo = modelo
        self.max_tokens = max_tokens

    @staticmethod
    def converter(sistema: str, mensagens: list[dict]) -> list[dict]:
        saida: list[dict] = [{"role": "system", "content": sistema}]
        for m in mensagens:
            if m["papel"] == "usuario":
                saida.append({"role": "user", "content": m["texto"]})
            elif m["papel"] == "assistente":
                msg: dict = {"role": "assistant", "content": m.get("texto") or None}
                if m.get("chamadas"):
                    msg["tool_calls"] = [
                        {"id": c["id"], "type": "function",
                         "function": {"name": c["nome"], "arguments": json.dumps(c["argumentos"], ensure_ascii=False)}}
                        for c in m["chamadas"]]
                saida.append(msg)
            elif m["papel"] == "ferramenta":
                saida.append({"role": "tool", "tool_call_id": m["id"],
                              "content": json.dumps(m["resultado"], ensure_ascii=False)})
        return saida

    def responder(self, sistema: str, mensagens: list[dict], ferramentas: list[Ferramenta]) -> RespostaLLM:
        r = self.cliente.chat.completions.create(
            model=self.modelo, max_completion_tokens=self.max_tokens,
            messages=self.converter(sistema, mensagens),
            tools=[{"type": "function", "function": {"name": f.nome, "description": f.descricao,
                                                     "parameters": f.parametros}} for f in ferramentas],
        )
        msg = r.choices[0].message
        chamadas = [Chamada(tc.id, tc.function.name, json.loads(tc.function.arguments or "{}"))
                    for tc in (msg.tool_calls or [])]
        uso = r.usage
        return RespostaLLM((msg.content or "").strip(), chamadas,
                           uso.prompt_tokens if uso else 0, uso.completion_tokens if uso else 0)
