"""Ferramentas que o agente pode chamar.

Cada ferramenta recebe o telefone de quem está conversando, e não um telefone
informado pelo modelo. Assim, mesmo que alguém peça "consulte o pedido 10512",
o bot só mostra pedidos que pertencem ao número que está falando com ele.
"""
from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

STATUS_LEGIVEL = {
    "aguardando_pagamento": "aguardando pagamento",
    "pago": "pagamento aprovado",
    "em_separacao": "em separação no estoque",
    "enviado": "enviado",
    "entregue": "entregue",
    "cancelado": "cancelado",
}

PRAZO_DEVOLUCAO = 7    # direito de arrependimento (CDC, art. 49) em compras online
PRAZO_TROCA = 30

POLITICAS = {
    "trocas e devoluções": (
        f"Devolução por arrependimento: até {PRAZO_DEVOLUCAO} dias corridos após o recebimento, com reembolso integral, "
        f"inclusive do frete. Troca por tamanho, cor ou modelo: até {PRAZO_TROCA} dias após o recebimento, com o produto "
        "sem uso e na embalagem original. Produto com defeito: até 90 dias, analisado pela assistência. "
        "A coleta é gratuita pelos Correios: enviamos um código de postagem após a abertura da solicitação."
    ),
    "frete e prazo de entrega": (
        "Frete grátis para compras acima de R$ 299 para Sul e Sudeste. Prazo de entrega: 3 a 7 dias úteis para capitais "
        "do Sul e Sudeste e 6 a 12 dias úteis para as demais regiões, contados após a aprovação do pagamento. "
        "O pedido é despachado em até 2 dias úteis."
    ),
    "formas de pagamento": (
        "Aceitamos Pix (5% de desconto, aprovação imediata), cartão de crédito em até 6x sem juros (parcela mínima "
        "de R$ 50) e boleto (aprovação em até 2 dias úteis). O pedido só é separado após a aprovação do pagamento."
    ),
    "garantia": (
        "Todos os produtos têm garantia legal de 90 dias. Eletroportáteis têm também garantia do fabricante de 12 meses; "
        "nesse caso, orientamos o cliente sobre a assistência técnica autorizada."
    ),
    "cancelamento": (
        "Pedidos podem ser cancelados sem custo antes do envio. Depois de enviado, o cliente pode recusar a entrega ou "
        "pedir a devolução por arrependimento. Reembolso: Pix e boleto em até 5 dias úteis; cartão, estorno na próxima "
        "fatura ou na seguinte."
    ),
    "atendimento": (
        "Atendimento humano de segunda a sexta, das 9h às 18h, e sábado, das 9h às 13h. Fora desse horário, o atendente "
        "responde no próximo período útil."
    ),
}


def _normalizar(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


@dataclass
class Contexto:
    con: sqlite3.Connection
    telefone: str
    hoje: date


# ------------------------------------------------------------------ implementações
def buscar_produtos(ctx: Contexto, termo: str, preco_max: float | None = None) -> dict:
    palavras = [p for p in _normalizar(termo).split() if len(p) > 2]
    linhas = ctx.con.execute("SELECT * FROM produtos").fetchall()
    resultados = []
    for p in linhas:
        texto = _normalizar(f"{p['nome']} {p['categoria']} {p['descricao']}")
        pontos = sum(1 for w in palavras if w in texto or (w.endswith("s") and w[:-1] in texto))
        if pontos and (preco_max is None or p["preco"] <= preco_max):
            resultados.append((pontos, p))
    # mantém só os mais aderentes: quem casa com quase todas as palavras buscadas
    melhor = max((pts for pts, _ in resultados), default=0)
    resultados = [(pts, p) for pts, p in resultados if pts >= max(1, melhor - 1)]
    resultados.sort(key=lambda x: (-x[0], x[1]["preco"]))
    return {
        "encontrados": len(resultados),
        "produtos": [
            {"sku": p["sku"], "nome": p["nome"], "preco": p["preco"],
             "disponivel": p["estoque"] > 0, "estoque": p["estoque"], "descricao": p["descricao"]}
            for _, p in resultados[:5]
        ],
    }


def _pedido_do_cliente(ctx: Contexto, numero: str) -> sqlite3.Row | None:
    numero = "".join(ch for ch in str(numero) if ch.isdigit())
    return ctx.con.execute(
        "SELECT * FROM pedidos WHERE numero = ? AND telefone = ?", (numero, ctx.telefone)).fetchone()


def consultar_pedido(ctx: Contexto, numero_pedido: str) -> dict:
    p = _pedido_do_cliente(ctx, numero_pedido)
    if not p:
        return {"erro": "Pedido não encontrado para este número de WhatsApp. Peça ao cliente para conferir o número "
                        "do pedido ou falar a partir do telefone usado na compra."}
    itens = ctx.con.execute(
        "SELECT pr.nome, i.quantidade, i.preco FROM itens_pedido i JOIN produtos pr USING (sku) WHERE i.numero = ?",
        (p["numero"],)).fetchall()
    return {
        "numero": p["numero"], "data_compra": p["data_compra"], "status": STATUS_LEGIVEL[p["status"]],
        "valor_total": p["valor_total"], "forma_pagamento": p["forma_pagamento"],
        "codigo_rastreio": p["codigo_rastreio"], "previsao_entrega": p["previsao_entrega"],
        "data_entrega": p["data_entrega"],
        "itens": [{"produto": i["nome"], "quantidade": i["quantidade"], "preco": i["preco"]} for i in itens],
    }


def listar_meus_pedidos(ctx: Contexto) -> dict:
    linhas = ctx.con.execute(
        "SELECT numero, data_compra, status, valor_total FROM pedidos WHERE telefone = ? ORDER BY data_compra DESC",
        (ctx.telefone,)).fetchall()
    if not linhas:
        return {"pedidos": [], "aviso": "Nenhum pedido encontrado para este número de WhatsApp."}
    return {"pedidos": [{"numero": r["numero"], "data_compra": r["data_compra"],
                         "status": STATUS_LEGIVEL[r["status"]], "valor_total": r["valor_total"]} for r in linhas]}


def consultar_politicas(ctx: Contexto, tema: str) -> dict:
    t = _normalizar(tema)
    chaves = {
        "trocas e devoluções": ["troc", "devol", "arrepend", "defeito", "reembols", "estorno"],
        "frete e prazo de entrega": ["frete", "prazo", "entreg", "envio", "chega", "demora"],
        "formas de pagamento": ["pag", "pix", "cartao", "boleto", "parcel", "desconto"],
        "garantia": ["garant", "assistencia", "quebr"],
        "cancelamento": ["cancel"],
        "atendimento": ["horario", "atendimento", "funciona"],
    }
    achados = [k for k, termos in chaves.items() if any(x in t for x in termos)]
    if not achados:
        return {"temas_disponiveis": list(POLITICAS), "aviso": "Tema não identificado."}
    return {k: POLITICAS[k] for k in achados}


def abrir_troca_devolucao(ctx: Contexto, numero_pedido: str, tipo: str, motivo: str) -> dict:
    p = _pedido_do_cliente(ctx, numero_pedido)
    if not p:
        return {"erro": "Pedido não encontrado para este número de WhatsApp."}
    if p["status"] != "entregue" or not p["data_entrega"]:
        return {"erro": f"Só é possível abrir troca ou devolução de pedidos entregues. Status atual: "
                        f"{STATUS_LEGIVEL[p['status']]}."}
    tipo = "devolucao" if _normalizar(tipo).startswith("devol") else "troca"
    dias = (ctx.hoje - date.fromisoformat(p["data_entrega"])).days
    limite = PRAZO_DEVOLUCAO if tipo == "devolucao" else PRAZO_TROCA
    if dias > limite:
        return {"erro": f"O prazo para {tipo} é de {limite} dias após a entrega, e o pedido foi entregue há {dias} dias. "
                        "Se o produto tiver defeito, ainda pode estar na garantia: ofereça transferir para um atendente.",
                "prazo_expirado": True}
    existente = ctx.con.execute("SELECT protocolo FROM solicitacoes WHERE numero = ?", (p["numero"],)).fetchone()
    if existente:
        return {"aviso": "Já existe uma solicitação aberta para este pedido.", "protocolo": existente["protocolo"]}
    protocolo = f"TR-{uuid.uuid4().hex[:6].upper()}"
    ctx.con.execute("INSERT INTO solicitacoes VALUES (?,?,?,?,?,?)",
                    (protocolo, p["numero"], ctx.telefone, tipo, motivo, ctx.hoje.isoformat()))
    ctx.con.commit()
    return {"protocolo": protocolo, "tipo": tipo, "pedido": p["numero"],
            "proximo_passo": "O código de postagem dos Correios será enviado por e-mail em até 1 dia útil."}


def transferir_para_humano(ctx: Contexto, motivo: str) -> dict:
    ctx.con.execute("UPDATE conversas SET status = 'humano', motivo_transferencia = ? WHERE telefone = ?",
                    (motivo, ctx.telefone))
    ctx.con.commit()
    return {"transferido": True, "aviso": "A conversa foi para a fila de atendimento humano. Não responda mais "
                                          "dúvidas; apenas avise o cliente que um atendente vai continuar."}


# ------------------------------------------------------------------ especificações (formato neutro)
@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict
    funcao: Callable[..., dict]


FERRAMENTAS: dict[str, Ferramenta] = {f.nome: f for f in [
    Ferramenta("buscar_produtos", "Busca produtos no catálogo da loja por palavras-chave, com preço e disponibilidade.",
               {"type": "object", "properties": {
                   "termo": {"type": "string", "description": "O que o cliente procura, ex.: 'jogo de cama casal'"},
                   "preco_max": {"type": "number", "description": "Preço máximo em reais, se o cliente informar"}},
                "required": ["termo"]}, buscar_produtos),
    Ferramenta("consultar_pedido", "Consulta status, itens, rastreio e previsão de entrega de um pedido do cliente.",
               {"type": "object", "properties": {"numero_pedido": {"type": "string"}}, "required": ["numero_pedido"]},
               consultar_pedido),
    Ferramenta("listar_meus_pedidos", "Lista os pedidos do cliente que está conversando (útil quando ele não sabe o número).",
               {"type": "object", "properties": {}}, listar_meus_pedidos),
    Ferramenta("consultar_politicas", "Consulta as regras oficiais da loja sobre trocas, devoluções, frete, prazos, "
                                      "pagamento, garantia, cancelamento e horário de atendimento.",
               {"type": "object", "properties": {"tema": {"type": "string"}}, "required": ["tema"]},
               consultar_politicas),
    Ferramenta("abrir_troca_devolucao", "Abre uma solicitação de troca ou devolução para um pedido entregue. "
                                        "Confirme o pedido e o motivo com o cliente antes de chamar.",
               {"type": "object", "properties": {
                   "numero_pedido": {"type": "string"},
                   "tipo": {"type": "string", "enum": ["troca", "devolucao"]},
                   "motivo": {"type": "string"}}, "required": ["numero_pedido", "tipo", "motivo"]},
               abrir_troca_devolucao),
    Ferramenta("transferir_para_humano", "Transfere a conversa para um atendente humano. Use quando o cliente pedir, "
                                         "estiver insatisfeito, ou o assunto fugir do que as ferramentas resolvem.",
               {"type": "object", "properties": {"motivo": {"type": "string"}}, "required": ["motivo"]},
               transferir_para_humano),
]}


def executar(nome: str, argumentos: dict[str, Any], ctx: Contexto) -> dict:
    f = FERRAMENTAS.get(nome)
    if not f:
        return {"erro": f"Ferramenta desconhecida: {nome}"}
    try:
        return f.funcao(ctx, **argumentos)
    except TypeError as e:
        return {"erro": f"Argumentos inválidos para {nome}: {e}"}
