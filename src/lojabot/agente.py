"""O agente: recebe a mensagem do cliente, decide quais ferramentas usar e responde."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from lojabot import db
from lojabot.config import Config
from lojabot.ferramentas import FERRAMENTAS, Contexto, executar
from lojabot.llm import ProvedorLLM

log = logging.getLogger(__name__)

MAX_RODADAS = 5  # limite de chamadas de ferramenta por mensagem (evita loops e custo descontrolado)

PROMPT_SISTEMA = """Você é o assistente virtual da {loja}, uma loja online de casa e decoração, atendendo pelo WhatsApp.
Data de hoje: {hoje}. Nome do cliente (se conhecido): {nome}.

Como responder:
- Português do Brasil, tom cordial e direto. Mensagens curtas, como no WhatsApp (no máximo 6 linhas).
- Formatação do WhatsApp: *negrito* com um asterisco, listas com "•". Nada de títulos ou tabelas em markdown.
- Valores em reais no formato R$ 1.234,56 e datas no formato dd/mm.

Regras:
- Use SEMPRE as ferramentas para informações de pedidos, produtos, estoque, preços e políticas. Nunca invente prazos,
  valores, códigos de rastreio ou regras.
- Os pedidos consultados são automaticamente filtrados pelo número de WhatsApp do cliente. Se um pedido não aparecer,
  oriente o cliente a conferir o número ou a falar do telefone usado na compra. Nunca tente contornar isso.
- Antes de abrir troca ou devolução, confirme o número do pedido e o motivo.
- Transfira para um humano quando o cliente pedir, demonstrar irritação, mencionar Procon, processo ou fraude, ou quando
  o assunto não puder ser resolvido com as ferramentas. Depois de transferir, apenas avise que um atendente vai continuar.
- Assuntos fora da loja: diga com educação que só pode ajudar com a {loja}.
"""


@dataclass
class Resultado:
    respostas: list[str] = field(default_factory=list)
    ferramentas: list[dict] = field(default_factory=list)
    transferido: bool = False
    em_atendimento_humano: bool = False


class Agente:
    def __init__(self, con: sqlite3.Connection, provedor: ProvedorLLM, cfg: Config, hoje: date | None = None):
        self.con, self.provedor, self.cfg = con, provedor, cfg
        self._hoje = hoje

    @property
    def hoje(self) -> date:
        return self._hoje or date.today()

    def processar(self, telefone: str, texto: str, nome: str | None = None, canal: str = "simulador") -> Resultado:
        conversa = db.garantir_conversa(self.con, telefone, nome, canal)
        db.salvar_mensagem(self.con, telefone, "usuario", {"papel": "usuario", "texto": texto})
        if conversa["status"] == "humano":
            # um atendente assumiu: o bot fica em silêncio e só registra a mensagem
            return Resultado(em_atendimento_humano=True)

        cliente = self.con.execute("SELECT nome FROM clientes WHERE telefone = ?", (telefone,)).fetchone()
        sistema = PROMPT_SISTEMA.format(loja=self.cfg.nome_loja, hoje=self.hoje.strftime("%d/%m/%Y"),
                                        nome=(cliente["nome"] if cliente else nome) or "não informado")
        historico = db.carregar_historico(self.con, telefone, self.cfg.historico_max)
        ctx = Contexto(self.con, telefone, self.hoje)
        resultado = Resultado()

        for _ in range(MAX_RODADAS):
            try:
                resp = self.provedor.responder(sistema, historico, list(FERRAMENTAS.values()))
            except Exception:  # falha da API de IA não pode deixar o cliente sem resposta
                log.exception("Falha ao chamar o provedor de IA")
                resultado.respostas.append("Desculpe, tive uma instabilidade aqui. Pode repetir em instantes? "
                                           "Se preferir, digite *atendente* para falar com a nossa equipe.")
                return resultado

            msg = {"papel": "assistente", "texto": resp.texto,
                   "chamadas": [{"id": c.id, "nome": c.nome, "argumentos": c.argumentos} for c in resp.chamadas]}
            historico.append(msg)
            db.salvar_mensagem(self.con, telefone, "assistente", msg)

            if resp.texto and not resp.chamadas:
                resultado.respostas.append(resp.texto)
                return resultado
            if resp.texto:  # texto intermediário ("vou verificar...") também vai para o cliente
                resultado.respostas.append(resp.texto)

            for c in resp.chamadas:
                saida = executar(c.nome, c.argumentos, ctx)
                self.con.execute("INSERT INTO uso_ferramentas (telefone, ferramenta, argumentos, criado_em) "
                                 "VALUES (?,?,?,?)", (telefone, c.nome, str(c.argumentos), db.agora()))
                resultado.ferramentas.append({"nome": c.nome, "argumentos": c.argumentos, "resultado": saida})
                if c.nome == "transferir_para_humano" and saida.get("transferido"):
                    resultado.transferido = True
                tool_msg = {"papel": "ferramenta", "id": c.id, "nome": c.nome, "resultado": saida}
                historico.append(tool_msg)
                db.salvar_mensagem(self.con, telefone, "ferramenta", tool_msg)
            self.con.commit()

        resultado.respostas.append("Vou chamar alguém da equipe para te ajudar com isso, só um instante.")
        executar("transferir_para_humano", {"motivo": "limite de rodadas do agente"}, ctx)
        resultado.transferido = True
        return resultado
