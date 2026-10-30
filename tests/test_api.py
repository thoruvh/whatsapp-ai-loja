import hashlib
import hmac
import json

from conftest import MARIANA

from lojabot.canais import evolution, meta


def payload_meta(texto="quais meus pedidos?", msg_id="wamid.1", tel=MARIANA, tipo="text"):
    m = {"from": tel, "id": msg_id, "timestamp": "1761700000", "type": tipo}
    if tipo == "text":
        m["text"] = {"body": texto}
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "contacts": [{"wa_id": tel, "profile": {"name": "Mariana"}}],
        "messages": [m]}}]}]}


def assinar(corpo: bytes, segredo="app-secret"):
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


def test_verificacao_do_webhook_meta(cliente_api):
    ok = cliente_api.get("/webhook/meta", params={"hub.mode": "subscribe", "hub.verify_token": "verifica",
                                                  "hub.challenge": "123"})
    assert ok.status_code == 200 and ok.text == "123"
    assert cliente_api.get("/webhook/meta", params={"hub.mode": "subscribe", "hub.verify_token": "errado",
                                                    "hub.challenge": "1"}).status_code == 403


def test_webhook_meta_responde_e_deduplica(cliente_api):
    corpo = json.dumps(payload_meta()).encode()
    h = {"X-Hub-Signature-256": assinar(corpo), "Content-Type": "application/json"}
    assert cliente_api.post("/webhook/meta", content=corpo, headers=h).json() == {"recebidas": 1}
    assert cliente_api.enviados and cliente_api.enviados[0][:2] == ("meta", MARIANA)
    # a Meta reenviou o mesmo evento: não responde de novo
    assert cliente_api.post("/webhook/meta", content=corpo, headers=h).json() == {"recebidas": 0}
    assert len(cliente_api.enviados) == 1


def test_webhook_meta_rejeita_assinatura_falsa(cliente_api):
    corpo = json.dumps(payload_meta(msg_id="wamid.2")).encode()
    r = cliente_api.post("/webhook/meta", content=corpo, headers={"X-Hub-Signature-256": assinar(corpo, "outro")})
    assert r.status_code == 401 and not cliente_api.enviados


def test_mensagem_nao_texto_recebe_aviso(cliente_api):
    corpo = json.dumps(payload_meta(msg_id="wamid.3", tipo="audio")).encode()
    cliente_api.post("/webhook/meta", content=corpo, headers={"X-Hub-Signature-256": assinar(corpo)})
    assert "apenas mensagens de texto" in cliente_api.enviados[0][2]


def test_webhook_evolution(cliente_api):
    evento = {"event": "messages.upsert", "instance": "loja", "data": {
        "key": {"remoteJid": f"{MARIANA}@s.whatsapp.net", "fromMe": False, "id": "ABC1"},
        "pushName": "Mariana", "message": {"conversation": "oi"}, "messageType": "conversation"}}
    assert cliente_api.post("/webhook/evolution?token=errado", json=evento).status_code == 401
    assert cliente_api.post("/webhook/evolution?token=tk", json=evento).json() == {"recebidas": 1}
    assert cliente_api.enviados[0][:2] == ("evolution", MARIANA)


def test_evolution_ignora_grupos_e_proprias_mensagens():
    base = {"event": "messages.upsert", "data": {"key": {"remoteJid": "123@g.us", "fromMe": False, "id": "1"},
                                                 "message": {"conversation": "oi"}}}
    assert evolution.extrair_mensagens(base) == []
    base["data"]["key"] = {"remoteJid": f"{MARIANA}@s.whatsapp.net", "fromMe": True, "id": "2"}
    assert evolution.extrair_mensagens(base) == []


def test_meta_ignora_eventos_de_status():
    status = {"entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "read"}]}}]}]}
    assert meta.extrair_mensagens(status) == []


def test_admin_exige_token_e_devolve_ao_bot(cliente_api):
    assert cliente_api.get("/admin/metricas").status_code == 401
    cliente_api.post("/api/chat", json={"telefone": MARIANA, "texto": "quero falar com um atendente"})
    h = {"X-Admin-Token": "segredo"}
    fila = cliente_api.get("/admin/conversas", params={"status": "humano"}, headers=h).json()
    assert [c["telefone"] for c in fila] == [MARIANA]
    assert cliente_api.post(f"/admin/conversas/{MARIANA}/devolver", headers=h).json() == {"status": "bot"}
    m = cliente_api.get("/admin/metricas", headers=h).json()
    assert m["transferidas_para_humano"] == 1 and m["aguardando_atendente"] == 0


def test_simulador_valida_entrada(cliente_api):
    assert cliente_api.post("/api/chat", json={"telefone": "abc", "texto": "oi"}).status_code == 422
    assert cliente_api.get("/simulador").status_code == 200
