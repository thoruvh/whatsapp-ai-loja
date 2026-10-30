from conftest import MARIANA

from lojabot import db
from lojabot.agente import MAX_RODADAS, Agente
from lojabot.llm.anthropic_llm import ProvedorAnthropic
from lojabot.llm.base import Chamada, RespostaLLM
from lojabot.llm.openai_llm import ProvedorOpenAI


def test_fluxo_completo_com_ferramenta(agente):
    r = agente.processar(MARIANA, "quais são meus pedidos?")
    assert [f["nome"] for f in r.ferramentas] == ["listar_meus_pedidos"]
    assert "pedidos" in r.respostas[0]
    hist = db.carregar_historico(agente.con, MARIANA, 50)
    assert [m["papel"] for m in hist] == ["usuario", "assistente", "ferramenta", "assistente"]


def test_transferencia_silencia_o_bot(agente):
    r = agente.processar(MARIANA, "quero falar com um atendente")
    assert r.transferido
    r2 = agente.processar(MARIANA, "alô?")
    assert r2.em_atendimento_humano and not r2.respostas


def test_historico_nunca_comeca_no_meio_de_ferramenta(agente):
    for _ in range(4):
        agente.processar(MARIANA, "quais meus pedidos")
    for limite in range(1, 12):
        hist = db.carregar_historico(agente.con, MARIANA, limite)
        assert not hist or hist[0]["papel"] == "usuario"


class ProvedorQuebrado:
    def responder(self, *a):
        raise TimeoutError("API fora do ar")


def test_falha_da_ia_responde_com_educacao(con, cfg):
    r = Agente(con, ProvedorQuebrado(), cfg).processar(MARIANA, "oi")
    assert "instabilidade" in r.respostas[0]


class ProvedorEmLoop:
    def responder(self, *a):
        return RespostaLLM(chamadas=[Chamada("x", "listar_meus_pedidos", {})])


def test_limite_de_rodadas_transfere(con, cfg):
    r = Agente(con, ProvedorEmLoop(), cfg).processar(MARIANA, "oi")
    assert r.transferido and len(r.ferramentas) == MAX_RODADAS


HIST = [
    {"papel": "usuario", "texto": "status do 10486"},
    {"papel": "assistente", "texto": "Vou verificar.", "chamadas": [
        {"id": "c1", "nome": "consultar_pedido", "argumentos": {"numero_pedido": "10486"}},
        {"id": "c2", "nome": "listar_meus_pedidos", "argumentos": {}}]},
    {"papel": "ferramenta", "id": "c1", "nome": "consultar_pedido", "resultado": {"status": "entregue"}},
    {"papel": "ferramenta", "id": "c2", "nome": "listar_meus_pedidos", "resultado": {"pedidos": []}},
]


def test_conversao_anthropic_agrupa_resultados():
    msgs = ProvedorAnthropic.converter(HIST)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert [b["type"] for b in msgs[1]["content"]] == ["text", "tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in msgs[2]["content"]] == ["c1", "c2"]


def test_conversao_openai():
    msgs = ProvedorOpenAI.converter("sistema", HIST)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "tool"]
    assert msgs[2]["tool_calls"][0]["function"]["name"] == "consultar_pedido"
    assert msgs[3]["tool_call_id"] == "c1"


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_anthropic_interpreta_resposta_com_ferramenta(agente):
    prov = ProvedorAnthropic.__new__(ProvedorAnthropic)
    prov.modelo, prov.max_tokens = "modelo-teste", 100
    resposta = _Obj(content=[_Obj(type="text", text="Vou ver."),
                             _Obj(type="tool_use", id="t1", name="listar_meus_pedidos", input={})],
                    usage=_Obj(input_tokens=10, output_tokens=5))
    prov.cliente = _Obj(messages=_Obj(create=lambda **kw: resposta))
    r = prov.responder("s", [{"papel": "usuario", "texto": "oi"}], [])
    assert r.texto == "Vou ver." and r.chamadas[0].nome == "listar_meus_pedidos"


def test_openai_interpreta_resposta_com_ferramenta():
    prov = ProvedorOpenAI.__new__(ProvedorOpenAI)
    prov.modelo, prov.max_tokens = "modelo-teste", 100
    tc = _Obj(id="c1", function=_Obj(name="consultar_pedido", arguments='{"numero_pedido": "10486"}'))
    resposta = _Obj(choices=[_Obj(message=_Obj(content=None, tool_calls=[tc]))],
                    usage=_Obj(prompt_tokens=10, completion_tokens=5))
    prov.cliente = _Obj(chat=_Obj(completions=_Obj(create=lambda **kw: resposta)))
    r = prov.responder("s", [{"papel": "usuario", "texto": "oi"}], [])
    assert r.chamadas[0].argumentos == {"numero_pedido": "10486"} and r.texto == ""
