"""API: webhooks do WhatsApp, simulador e painel administrativo.

    uvicorn lojabot.app:app --reload
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

from lojabot import db
from lojabot.agente import Agente
from lojabot.canais import evolution, meta
from lojabot.canais.meta import MensagemRecebida
from lojabot.config import Config, carregar
from lojabot.llm import criar_provedor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lojabot")
ESTATICOS = Path(__file__).parent / "static"
AVISO_NAO_TEXTO = "Por enquanto consigo ler apenas mensagens de texto. Pode escrever sua dúvida?"


class Estado:
    cfg: Config
    agente: Agente
    trava = threading.Lock()  # SQLite + uma conexão: processa uma mensagem por vez


estado = Estado()


def iniciar(cfg: Config | None = None, popular: bool = True) -> None:
    estado.cfg = cfg or carregar()
    con = db.conectar(estado.cfg.banco)
    if popular:
        db.popular_demo(con)
    estado.agente = Agente(con, criar_provedor(estado.cfg), estado.cfg)
    log.info("Bot iniciado: IA=%s (%s), canal=%s", estado.cfg.llm_provedor, estado.cfg.modelo, estado.cfg.canal)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    if not hasattr(estado, "agente"):
        iniciar()
    yield


app = FastAPI(title="Bot de atendimento WhatsApp com IA", version="0.1.0", lifespan=ciclo_de_vida)


# ------------------------------------------------------------------ processamento comum
async def _enviar(canal: str, telefone: str, texto: str) -> None:
    if canal == "meta":
        await meta.enviar_texto(estado.cfg, telefone, texto)
    elif canal == "evolution":
        await evolution.enviar_texto(estado.cfg, telefone, texto)


async def _atender(m: MensagemRecebida, canal: str) -> None:
    try:
        if not m.texto:
            await _enviar(canal, m.telefone, AVISO_NAO_TEXTO)
            return
        with estado.trava:
            resultado = estado.agente.processar(m.telefone, m.texto, m.nome, canal)
        for resposta in resultado.respostas:
            await _enviar(canal, m.telefone, resposta)
    except Exception:
        log.exception("Erro ao atender %s", m.telefone)


def _agendar(mensagens: list[MensagemRecebida], canal: str, tarefas: BackgroundTasks) -> int:
    novas = 0
    for m in mensagens:
        with estado.trava:
            repetida = db.ja_recebida(estado.agente.con, f"{canal}:{m.id}")
        if not repetida:
            tarefas.add_task(_atender, m, canal)  # responde 200 já; a IA roda em segundo plano
            novas += 1
    return novas


# ------------------------------------------------------------------ WhatsApp Cloud API (Meta)
@app.get("/webhook/meta", response_class=PlainTextResponse)
def meta_verificar(modo: str = Query(alias="hub.mode", default=""), token: str = Query(alias="hub.verify_token", default=""),
                   desafio: str = Query(alias="hub.challenge", default="")):
    if modo == "subscribe" and token and token == estado.cfg.meta_verify_token:
        return desafio
    raise HTTPException(403, "Token de verificação inválido")


@app.post("/webhook/meta")
async def meta_receber(request: Request, tarefas: BackgroundTasks):
    corpo = await request.body()
    if not meta.assinatura_valida(corpo, request.headers.get("X-Hub-Signature-256"), estado.cfg.meta_app_secret):
        raise HTTPException(401, "Assinatura inválida")
    return {"recebidas": _agendar(meta.extrair_mensagens(await request.json()), "meta", tarefas)}


# ------------------------------------------------------------------ Evolution API
@app.post("/webhook/evolution")
async def evolution_receber(request: Request, tarefas: BackgroundTasks, token: str = ""):
    if estado.cfg.evolution_webhook_token and token != estado.cfg.evolution_webhook_token:
        raise HTTPException(401, "Token inválido")
    return {"recebidas": _agendar(evolution.extrair_mensagens(await request.json()), "evolution", tarefas)}


# ------------------------------------------------------------------ simulador (teste sem WhatsApp)
class MensagemSimulador(BaseModel):
    telefone: str = Field(pattern=r"^\d{10,15}$")
    texto: str = Field(min_length=1, max_length=2000)


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse("/simulador")


@app.get("/simulador", include_in_schema=False)
def simulador():
    return FileResponse(ESTATICOS / "simulador.html")


@app.get("/api/clientes-demo")
def clientes_demo():
    linhas = estado.agente.con.execute(
        "SELECT c.telefone, c.nome, COUNT(p.numero) pedidos FROM clientes c LEFT JOIN pedidos p USING (telefone) "
        "GROUP BY 1, 2 ORDER BY 2").fetchall()
    return {"clientes": [dict(r) for r in linhas], "provedor": estado.cfg.llm_provedor, "modelo": estado.cfg.modelo,
            "loja": estado.cfg.nome_loja}


@app.post("/api/chat")
def chat(m: MensagemSimulador):
    with estado.trava:
        return asdict(estado.agente.processar(m.telefone, m.texto, canal="simulador"))


@app.post("/api/simulador/reiniciar/{telefone}")
def reiniciar(telefone: str):
    if estado.cfg.canal != "nenhum":
        raise HTTPException(403, "Disponível apenas no modo simulador (CANAL=nenhum)")
    with estado.trava:
        con = estado.agente.con
        con.execute("DELETE FROM mensagens WHERE telefone = ?", (telefone,))
        con.execute("DELETE FROM conversas WHERE telefone = ?", (telefone,))
        con.execute("DELETE FROM solicitacoes WHERE telefone = ?", (telefone,))
        con.commit()
    return {"ok": True}


# ------------------------------------------------------------------ painel administrativo
def exigir_admin(x_admin_token: str = Header(default="")):
    if x_admin_token != estado.cfg.admin_token:
        raise HTTPException(401, "Token de administrador inválido")


admin = Depends(exigir_admin)


@app.get("/admin/conversas", dependencies=[admin])
def listar_conversas(status: str | None = None):
    sql = "SELECT * FROM conversas" + (" WHERE status = ?" if status else "") + " ORDER BY atualizado_em DESC"
    return [dict(r) for r in estado.agente.con.execute(sql, (status,) if status else ()).fetchall()]


@app.get("/admin/conversas/{telefone}/mensagens", dependencies=[admin])
def mensagens(telefone: str):
    return db.carregar_historico(estado.agente.con, telefone, 200)


class RespostaHumana(BaseModel):
    texto: str = Field(min_length=1, max_length=4096)


@app.post("/admin/conversas/{telefone}/responder", dependencies=[admin])
async def responder_como_humano(telefone: str, r: RespostaHumana):
    conversa = estado.agente.con.execute("SELECT canal FROM conversas WHERE telefone = ?", (telefone,)).fetchone()
    if not conversa:
        raise HTTPException(404, "Conversa não encontrada")
    db.salvar_mensagem(estado.agente.con, telefone, "humano", {"papel": "humano", "texto": r.texto})
    await _enviar(conversa["canal"], telefone, r.texto)
    return {"enviado": True}


@app.post("/admin/conversas/{telefone}/devolver", dependencies=[admin])
def devolver_ao_bot(telefone: str):
    estado.agente.con.execute("UPDATE conversas SET status = 'bot' WHERE telefone = ?", (telefone,))
    estado.agente.con.commit()
    return {"status": "bot"}


@app.get("/admin/metricas", dependencies=[admin])
def metricas():
    con = estado.agente.con
    total = con.execute("SELECT COUNT(*) FROM conversas").fetchone()[0]
    humanas = con.execute("SELECT COUNT(*) FROM conversas WHERE motivo_transferencia IS NOT NULL").fetchone()[0]
    ferramentas = con.execute("SELECT ferramenta, COUNT(*) n FROM uso_ferramentas GROUP BY 1 ORDER BY 2 DESC").fetchall()
    return {
        "conversas": total,
        "mensagens_de_clientes": con.execute("SELECT COUNT(*) FROM mensagens WHERE papel = 'usuario'").fetchone()[0],
        "resolvidas_sem_humano": (total - humanas) / total if total else None,
        "transferidas_para_humano": humanas,
        "aguardando_atendente": con.execute("SELECT COUNT(*) FROM conversas WHERE status = 'humano'").fetchone()[0],
        "trocas_devolucoes_abertas": con.execute("SELECT COUNT(*) FROM solicitacoes").fetchone()[0],
        "uso_de_ferramentas": {r["ferramenta"]: r["n"] for r in ferramentas},
    }


@app.get("/saude")
def saude():
    return {"ok": True, "ia": estado.cfg.llm_provedor, "canal": estado.cfg.canal}
