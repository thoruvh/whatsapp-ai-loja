"""Interface comum para os provedores de IA.

O histórico é guardado num formato neutro, então dá para trocar de provedor
(ou de modelo) sem perder as conversas em andamento:

    {"papel": "usuario",     "texto": "..."}
    {"papel": "assistente",  "texto": "...", "chamadas": [{"id", "nome", "argumentos"}]}
    {"papel": "ferramenta",  "id": "...", "nome": "...", "resultado": {...}}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from lojabot.ferramentas import Ferramenta


@dataclass
class Chamada:
    id: str
    nome: str
    argumentos: dict


@dataclass
class RespostaLLM:
    texto: str = ""
    chamadas: list[Chamada] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_saida: int = 0


class ProvedorLLM(Protocol):
    def responder(self, sistema: str, mensagens: list[dict], ferramentas: list[Ferramenta]) -> RespostaLLM: ...
