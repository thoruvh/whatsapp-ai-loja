"""Provedor de demonstração: regras simples no lugar da IA.

Serve para rodar o projeto e os testes sem chave de API. Ele passa pelo mesmo
caminho do agente (decide uma ferramenta, recebe o resultado e responde), mas
entende só frases simples. Em produção, use LLM_PROVEDOR=anthropic ou openai.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date

from lojabot.ferramentas import Ferramenta
from lojabot.llm.base import Chamada, RespostaLLM

PARADAS = set("""a o as os um uma de da do das dos e em no na nos nas para pra por com que se eu voce voces me meu minha
quero queria gostaria procuro procurando tem tens teria vende vendem algum alguma ai ola oi bom dia boa tarde noite preciso
comprar ver saber qual quais quanto custa valor preco ate reais rs sobre isso esse essa""".split())


def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m") if iso else "-"


class ProvedorDemo:
    def __init__(self, nome_loja: str = "Casa Aurora"):
        self.nome_loja = nome_loja

    def responder(self, sistema: str, mensagens: list[dict], ferramentas: list[Ferramenta]) -> RespostaLLM:
        ultima = mensagens[-1]
        if ultima["papel"] == "ferramenta":
            return RespostaLLM(self._redigir(ultima["nome"], ultima["resultado"]))
        return self._decidir(ultima["texto"], mensagens)

    # ------------------------------------------------------------ decide a ferramenta
    def _chamar(self, nome: str, **args) -> RespostaLLM:
        return RespostaLLM(chamadas=[Chamada(f"demo_{uuid.uuid4().hex[:8]}", nome, args)])

    def _decidir(self, texto: str, mensagens: list[dict]) -> RespostaLLM:
        t = _norm(texto)
        numero = re.search(r"\b(1\d{4})\b", t)
        anterior = next((m.get("texto", "") for m in reversed(mensagens[:-1])
                         if m["papel"] == "assistente" and m.get("texto")), "")
        quer_troca = re.search(r"troc|devolv|devoluc|arrepend", t)

        if re.search(r"atendente|humano|pessoa|falar com alguem|reclama|procon", t):
            return self._chamar("transferir_para_humano", motivo=texto)
        if numero and (quer_troca or "numero do pedido para abrir" in _norm(anterior)):
            pedido_troca = next((m["texto"] for m in reversed(mensagens) if m["papel"] == "usuario"
                                 and re.search(r"troc|devolv|devoluc|arrepend", _norm(m["texto"]))), texto)
            tipo = "devolucao" if re.search(r"devolv|devoluc|arrepend|reembols", _norm(pedido_troca)) else "troca"
            return self._chamar("abrir_troca_devolucao", numero_pedido=numero.group(1), tipo=tipo, motivo=pedido_troca)
        if quer_troca and re.search(r"quero|preciso|gostaria|como faco|abrir", t):
            return RespostaLLM("Claro! Me passa o número do pedido para abrir a solicitação? "
                               "Ele começa com 1 e tem 5 dígitos.")
        if numero:
            return self._chamar("consultar_pedido", numero_pedido=numero.group(1))
        if re.search(r"meus pedidos|meu pedido|minha compra|minhas compras|cade|rastre|status", t):
            return self._chamar("listar_meus_pedidos")
        tema = re.search(r"troc|devol|frete|prazo|entreg|pag|pix|cartao|boleto|parcel|garant|cancel|horario", t)
        if tema:
            return self._chamar("consultar_politicas", tema=texto)
        palavras = [w for w in re.findall(r"[a-z]+", t) if w not in PARADAS and len(w) > 2]
        if palavras and not re.fullmatch(r"(obrigad[oa]|valeu|ok|tchau|beleza)", t.strip(" !.")):
            preco = re.search(r"ate\s*(?:r\$\s*)?(\d+)", t)
            args = {"termo": " ".join(palavras)}
            if preco:
                args["preco_max"] = float(preco.group(1))
            return self._chamar("buscar_produtos", **args)
        if re.search(r"obrigad|valeu", t):
            return RespostaLLM("Por nada! Se precisar de mais alguma coisa, é só chamar. 😊")
        return RespostaLLM(f"Olá! Sou o assistente virtual da {self.nome_loja}. Posso consultar seus pedidos, "
                           "ajudar a encontrar produtos, tirar dúvidas sobre frete e pagamento ou abrir uma troca. "
                           "Como posso ajudar?")

    # ------------------------------------------------------------ redige a resposta
    def _redigir(self, nome: str, r: dict) -> str:
        if "erro" in r:
            return r["erro"].split(". ")[0].rstrip(".") + "."
        if nome == "consultar_pedido":
            itens = "\n".join(f"• {i['quantidade']}x {i['produto']}" for i in r["itens"])
            linhas = [f"*Pedido {r['numero']}*: {r['status']}", itens, f"Total: {brl(r['valor_total'])}"]
            if r["data_entrega"]:
                linhas.append(f"Entregue em {data_br(r['data_entrega'])}.")
            elif r["codigo_rastreio"]:
                linhas.append(f"Rastreio: {r['codigo_rastreio']} · previsão {data_br(r['previsao_entrega'])}")
            elif r["previsao_entrega"]:
                linhas.append(f"Previsão de entrega: {data_br(r['previsao_entrega'])}")
            return "\n".join(linhas)
        if nome == "listar_meus_pedidos":
            if not r["pedidos"]:
                return r["aviso"]
            linhas = [f"• *{p['numero']}* ({data_br(p['data_compra'])}): {p['status']}, {brl(p['valor_total'])}"
                      for p in r["pedidos"]]
            return "Encontrei estes pedidos no seu número:\n" + "\n".join(linhas) + \
                "\n\nQuer detalhes de algum? É só mandar o número."
        if nome == "buscar_produtos":
            if not r["produtos"]:
                return "Não encontrei esse produto no catálogo. Pode descrever de outro jeito?"
            linhas = [f"• {p['nome']}: {brl(p['preco'])}" + ("" if p["disponivel"] else " _(esgotado)_")
                      for p in r["produtos"]]
            return "Olha o que encontrei:\n" + "\n".join(linhas)
        if nome == "consultar_politicas":
            if "aviso" in r:
                return "Posso explicar trocas, frete, pagamento, garantia ou cancelamento. Qual desses?"
            return "\n\n".join(r.values())
        if nome == "abrir_troca_devolucao":
            if "aviso" in r:
                return f"{r['aviso']} Protocolo: {r['protocolo']}."
            return (f"Pronto! Abri a solicitação de {'devolução' if r['tipo'] == 'devolucao' else 'troca'} do pedido "
                    f"{r['pedido']}. Protocolo: *{r['protocolo']}*. {r['proximo_passo']}")
        if nome == "transferir_para_humano":
            return "Entendi. Vou te passar para um atendente da nossa equipe, que continua por aqui mesmo. 🙋"
        return "Certo!"
