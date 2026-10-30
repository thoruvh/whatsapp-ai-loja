"""Evolution API (v2): conexão não oficial via WhatsApp Web, por QR code.

Atenção: por não ser oficial, o número pode ser bloqueado pelo WhatsApp. Para
operação de empresa, prefira a Cloud API (canais/meta.py).
Documentação: https://doc.evolution-api.com
"""
from __future__ import annotations

import httpx

from lojabot.canais.meta import MensagemRecebida
from lojabot.config import Config


def extrair_mensagens(payload: dict) -> list[MensagemRecebida]:
    """Lê o evento messages.upsert. Ignora mensagens enviadas pela própria conta e de grupos."""
    evento = (payload.get("event") or "").lower().replace("_", ".")
    if evento != "messages.upsert":
        return []
    dados = payload.get("data") or {}
    itens = dados if isinstance(dados, list) else [dados]
    saida = []
    for d in itens:
        chave = d.get("key", {})
        jid = chave.get("remoteJid", "")
        if chave.get("fromMe") or not jid.endswith("@s.whatsapp.net"):
            continue
        msg = d.get("message") or {}
        texto = msg.get("conversation") or (msg.get("extendedTextMessage") or {}).get("text")
        tipo = "text" if texto else (d.get("messageType") or "desconhecido")
        saida.append(MensagemRecebida(chave.get("id", ""), jid.split("@")[0], texto, d.get("pushName"), tipo))
    return saida


async def enviar_texto(cfg: Config, telefone: str, texto: str, cliente: httpx.AsyncClient | None = None) -> None:
    url = f"{cfg.evolution_url.rstrip('/')}/message/sendText/{cfg.evolution_instancia}"
    async with (cliente or httpx.AsyncClient(timeout=15)) as c:
        r = await c.post(url, json={"number": telefone, "text": texto}, headers={"apikey": cfg.evolution_api_key})
        r.raise_for_status()
