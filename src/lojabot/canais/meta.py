"""WhatsApp Cloud API (oficial da Meta).

Documentação: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

import httpx

from lojabot.config import Config


@dataclass
class MensagemRecebida:
    id: str
    telefone: str
    texto: str | None
    nome: str | None
    tipo: str


def assinatura_valida(corpo: bytes, cabecalho: str | None, app_secret: str) -> bool:
    """Confere o cabeçalho X-Hub-Signature-256, que prova que o webhook veio da Meta."""
    if not app_secret:
        return True  # ambiente local sem segredo configurado
    if not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = hmac.new(app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho.removeprefix("sha256="))


def extrair_mensagens(payload: dict) -> list[MensagemRecebida]:
    """Extrai as mensagens de um webhook. Eventos de status (entregue, lido) são ignorados."""
    saida = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            valor = change.get("value", {})
            nomes = {c.get("wa_id"): c.get("profile", {}).get("name") for c in valor.get("contacts", [])}
            for m in valor.get("messages", []):
                tipo = m.get("type", "")
                texto = None
                if tipo == "text":
                    texto = m["text"]["body"]
                elif tipo == "button":
                    texto = m["button"].get("text")
                elif tipo == "interactive":
                    i = m["interactive"]
                    texto = (i.get("button_reply") or i.get("list_reply") or {}).get("title")
                saida.append(MensagemRecebida(m["id"], m["from"], texto, nomes.get(m["from"]), tipo))
    return saida


async def enviar_texto(cfg: Config, telefone: str, texto: str, cliente: httpx.AsyncClient | None = None) -> None:
    url = f"https://graph.facebook.com/{cfg.meta_api_versao}/{cfg.meta_phone_number_id}/messages"
    corpo = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": telefone,
             "type": "text", "text": {"preview_url": False, "body": texto[:4096]}}
    async with (cliente or httpx.AsyncClient(timeout=15)) as c:
        r = await c.post(url, json=corpo, headers={"Authorization": f"Bearer {cfg.meta_token}"})
        r.raise_for_status()
