from datetime import timedelta

from conftest import HOJE, JULIANA, MARIANA

from lojabot.ferramentas import Contexto, executar


def ctx(con, tel=MARIANA, hoje=HOJE):
    con.execute("INSERT OR IGNORE INTO conversas (telefone, status) VALUES (?, 'bot')", (tel,))
    return Contexto(con, tel, hoje)


def pedido_de(con, tel, status=None):
    sql = "SELECT * FROM pedidos WHERE telefone = ?" + (" AND status = ?" if status else "")
    return con.execute(sql, (tel, status) if status else (tel,)).fetchone()


def test_cliente_nao_ve_pedido_de_outro(con):
    pedido_juliana = pedido_de(con, JULIANA)["numero"]
    r = executar("consultar_pedido", {"numero_pedido": pedido_juliana}, ctx(con, MARIANA))
    assert "erro" in r and "itens" not in r


def test_consulta_pedido_proprio(con):
    p = pedido_de(con, MARIANA)
    r = executar("consultar_pedido", {"numero_pedido": f"#{p['numero']}"}, ctx(con))
    assert r["numero"] == p["numero"] and r["itens"]


def test_listar_pedidos_so_do_proprio_numero(con):
    r = executar("listar_meus_pedidos", {}, ctx(con, MARIANA))
    numeros = {p["numero"] for p in r["pedidos"]}
    donos = {row[0] for row in con.execute(
        f"SELECT telefone FROM pedidos WHERE numero IN ({','.join('?' * len(numeros))})", tuple(numeros))}
    assert donos == {MARIANA}


def test_busca_respeita_preco_maximo(con):
    r = executar("buscar_produtos", {"termo": "jogo de cama", "preco_max": 300}, ctx(con))
    assert r["produtos"] and all(p["preco"] <= 300 for p in r["produtos"])


def test_politicas_por_tema(con):
    r = executar("consultar_politicas", {"tema": "posso pagar com pix?"}, ctx(con))
    assert "formas de pagamento" in r


def test_devolucao_dentro_do_prazo(con):
    p = con.execute("SELECT * FROM pedidos WHERE status = 'entregue' ORDER BY data_entrega DESC").fetchone()
    hoje = __import__("datetime").date.fromisoformat(p["data_entrega"]) + timedelta(days=3)
    r = executar("abrir_troca_devolucao", {"numero_pedido": p["numero"], "tipo": "devolucao", "motivo": "arrependimento"},
                 ctx(con, p["telefone"], hoje))
    assert r["protocolo"].startswith("TR-")
    # segunda tentativa não duplica
    r2 = executar("abrir_troca_devolucao", {"numero_pedido": p["numero"], "tipo": "devolucao", "motivo": "x"},
                  ctx(con, p["telefone"], hoje))
    assert r2["protocolo"] == r["protocolo"]


def test_devolucao_fora_do_prazo(con):
    p = con.execute("SELECT * FROM pedidos WHERE status = 'entregue'").fetchone()
    hoje = __import__("datetime").date.fromisoformat(p["data_entrega"]) + timedelta(days=8)
    r = executar("abrir_troca_devolucao", {"numero_pedido": p["numero"], "tipo": "devolucao", "motivo": "x"},
                 ctx(con, p["telefone"], hoje))
    assert r.get("prazo_expirado")


def test_troca_exige_pedido_entregue(con):
    p = con.execute("SELECT * FROM pedidos WHERE status = 'enviado'").fetchone()
    r = executar("abrir_troca_devolucao", {"numero_pedido": p["numero"], "tipo": "troca", "motivo": "x"},
                 ctx(con, p["telefone"]))
    assert "erro" in r


def test_ferramenta_inexistente_e_argumento_invalido(con):
    assert "erro" in executar("apagar_banco", {}, ctx(con))
    assert "erro" in executar("consultar_pedido", {"pedido": "1"}, ctx(con))
