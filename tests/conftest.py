from datetime import date

import pytest
from fastapi.testclient import TestClient

from lojabot import app as app_mod
from lojabot import db
from lojabot.agente import Agente
from lojabot.config import Config
from lojabot.llm.demo_llm import ProvedorDemo

HOJE = date(2026, 10, 29)
MARIANA = "5511987650001"
JULIANA = "5521998760003"


@pytest.fixture
def con():
    c = db.conectar(":memory:")
    db.popular_demo(c, hoje=HOJE)
    yield c
    c.close()


@pytest.fixture
def cfg():
    return Config(banco=":memory:", llm_provedor="demo", canal="nenhum", admin_token="segredo",
                  meta_app_secret="app-secret", meta_verify_token="verifica", evolution_webhook_token="tk")


@pytest.fixture
def agente(con, cfg):
    return Agente(con, ProvedorDemo(), cfg, hoje=HOJE)


@pytest.fixture
def cliente_api(cfg, monkeypatch):
    app_mod.iniciar(cfg)
    app_mod.estado.agente._hoje = HOJE
    enviados = []

    async def falso_enviar(canal, telefone, texto):
        enviados.append((canal, telefone, texto))

    monkeypatch.setattr(app_mod, "_enviar", falso_enviar)
    with TestClient(app_mod.app) as c:
        c.enviados = enviados
        yield c
