"""Adaptador para a API da Anthropic (Claude)."""
from __future__ import annotations

import json

from lojabot.ferramentas import Ferramenta
from lojabot.llm.base import Chamada, RespostaLLM


class ProvedorAnthropic:
    def __init__(self, api_key: str, modelo: str, max_tokens: int = 800):
        import anthropic

        self.cliente = anthropic.Anthropic(api_key=api_key)
        self.modelo = modelo
        self.max_tokens = max_tokens

    @staticmethod
    def converter(mensagens: list[dict]) -> list[dict]:
        saida: list[dict] = []
        for m in mensagens:
            if m["papel"] == "usuario":
                saida.append({"role": "user", "content": m["texto"]})
            elif m["papel"] == "assistente":
                blocos: list[dict] = []
                if m.get("texto"):
                    blocos.append({"type": "text", "text": m["texto"]})
                for c in m.get("chamadas", []):
                    blocos.append({"type": "tool_use", "id": c["id"], "name": c["nome"], "input": c["argumentos"]})
                saida.append({"role": "assistant", "content": blocos})
            elif m["papel"] == "ferramenta":
                bloco = {"type": "tool_result", "tool_use_id": m["id"],
                         "content": json.dumps(m["resultado"], ensure_ascii=False)}
                # resultados consecutivos vão juntos numa única mensagem do usuário
                if saida and saida[-1]["role"] == "user" and isinstance(saida[-1]["content"], list):
                    saida[-1]["content"].append(bloco)
                else:
                    saida.append({"role": "user", "content": [bloco]})
        return saida

    def responder(self, sistema: str, mensagens: list[dict], ferramentas: list[Ferramenta]) -> RespostaLLM:
        r = self.cliente.messages.create(
            model=self.modelo, max_tokens=self.max_tokens, system=sistema,
            messages=self.converter(mensagens),
            tools=[{"name": f.nome, "description": f.descricao, "input_schema": f.parametros} for f in ferramentas],
        )
        texto = "".join(b.text for b in r.content if b.type == "text")
        chamadas = [Chamada(b.id, b.name, dict(b.input)) for b in r.content if b.type == "tool_use"]
        return RespostaLLM(texto.strip(), chamadas, r.usage.input_tokens, r.usage.output_tokens)
