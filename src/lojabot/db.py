"""Banco SQLite da loja e das conversas.

Em produção, as tabelas `produtos`, `clientes` e `pedidos` seriam substituídas por
chamadas à API da plataforma da loja (Shopify, Nuvemshop, VTEX, Bling...). O agente
só conhece as funções de `ferramentas.py`, então trocar a fonte não muda o bot.
"""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS produtos (
    sku TEXT PRIMARY KEY, nome TEXT, categoria TEXT, preco REAL, estoque INTEGER, descricao TEXT
);
CREATE TABLE IF NOT EXISTS clientes (
    telefone TEXT PRIMARY KEY, nome TEXT, email TEXT
);
CREATE TABLE IF NOT EXISTS pedidos (
    numero TEXT PRIMARY KEY, telefone TEXT REFERENCES clientes(telefone), data_compra TEXT,
    status TEXT, valor_total REAL, forma_pagamento TEXT, codigo_rastreio TEXT,
    previsao_entrega TEXT, data_entrega TEXT
);
CREATE TABLE IF NOT EXISTS itens_pedido (
    numero TEXT REFERENCES pedidos(numero), sku TEXT REFERENCES produtos(sku), quantidade INTEGER, preco REAL
);
CREATE TABLE IF NOT EXISTS solicitacoes (
    protocolo TEXT PRIMARY KEY, numero TEXT, telefone TEXT, tipo TEXT, motivo TEXT, criado_em TEXT
);
CREATE TABLE IF NOT EXISTS conversas (
    telefone TEXT PRIMARY KEY, nome TEXT, status TEXT DEFAULT 'bot', canal TEXT,
    criado_em TEXT, atualizado_em TEXT, motivo_transferencia TEXT
);
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT, telefone TEXT, papel TEXT, conteudo TEXT, criado_em TEXT
);
CREATE TABLE IF NOT EXISTS uso_ferramentas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, telefone TEXT, ferramenta TEXT, argumentos TEXT, criado_em TEXT
);
CREATE TABLE IF NOT EXISTS mensagens_recebidas (
    id_externo TEXT PRIMARY KEY, recebido_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_mensagens_tel ON mensagens(telefone, id);
"""


def conectar(caminho: str) -> sqlite3.Connection:
    if caminho != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    return con


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ dados de demonstração
PRODUTOS = [
    ("CA-001", "Jogo de panelas antiaderente 5 peças", "Cozinha", 459.90, 14, "Alumínio com revestimento cerâmico, tampas de vidro."),
    ("CA-002", "Frigideira de ferro fundido 26 cm", "Cozinha", 189.90, 22, "Pré-curada, vai ao forno."),
    ("CA-003", "Faqueiro inox 24 peças", "Cozinha", 229.00, 9, "Aço inox 18/10, acompanha estojo."),
    ("CA-004", "Cafeteira italiana 6 xícaras", "Cozinha", 119.90, 31, "Alumínio, compatível com fogão a gás e elétrico."),
    ("CA-005", "Conjunto de potes herméticos de vidro 10 peças", "Cozinha", 149.90, 0, "Tampas com trava e vedação de silicone."),
    ("CA-006", "Tábua de corte em bambu grande", "Cozinha", 69.90, 40, "48 x 30 cm, com canaleta."),
    ("CA-007", "Liquidificador 1200 W 3 litros", "Eletroportáteis", 299.90, 12, "12 velocidades, jarra de vidro."),
    ("CA-008", "Air fryer 5 litros digital", "Eletroportáteis", 529.00, 7, "8 programas, timer de 60 min."),
    ("CA-009", "Chaleira elétrica inox 1,7 litro", "Eletroportáteis", 159.90, 18, "Desligamento automático."),
    ("CA-010", "Jogo de cama casal 4 peças 200 fios", "Cama e banho", 249.90, 25, "100% algodão, cor areia."),
    ("CA-011", "Jogo de cama queen 4 peças 400 fios", "Cama e banho", 389.90, 11, "Percal 100% algodão, cor branca."),
    ("CA-012", "Toalha de banho gigante felpuda", "Cama e banho", 79.90, 60, "90 x 150 cm, algodão egípcio."),
    ("CA-013", "Edredom casal dupla face", "Cama e banho", 219.90, 0, "Microfibra, cinza e off-white."),
    ("CA-014", "Travesseiro de látex", "Cama e banho", 179.90, 15, "Altura média, capa removível."),
    ("CA-015", "Luminária de mesa articulada", "Decoração", 139.90, 20, "LED, três tons de luz."),
    ("CA-016", "Espelho redondo moldura dourada 60 cm", "Decoração", 289.90, 6, "Fixação na parede inclusa."),
    ("CA-017", "Vaso cerâmica artesanal médio", "Decoração", 99.90, 13, "Cor terracota, 25 cm de altura."),
    ("CA-018", "Kit 3 quadros decorativos abstratos", "Decoração", 199.90, 8, "40 x 60 cm cada, moldura preta."),
    ("CA-019", "Tapete sala 2 x 1,4 m", "Decoração", 349.90, 5, "Pelo baixo, antiderrapante."),
    ("CA-020", "Cortina blackout 2,8 x 2,3 m", "Decoração", 169.90, 17, "Bloqueia 90% da luz."),
    ("CA-021", "Organizador de gavetas 6 peças", "Organização", 59.90, 45, "Plástico reciclado."),
    ("CA-022", "Cesto de roupa em fibra natural", "Organização", 129.90, 10, "Com tampa e alças."),
    ("CA-023", "Sapateira vertical 12 pares", "Organização", 189.90, 4, "MDF branco."),
    ("CA-024", "Aspirador de pó vertical sem fio", "Eletroportáteis", 699.00, 3, "Bateria de 40 min, filtro HEPA."),
    ("CA-025", "Ferro de passar a vapor", "Eletroportáteis", 149.90, 21, "Base cerâmica, 1400 W."),
]

CLIENTES = [
    ("5511987650001", "Mariana Costa", "mariana@example.com"),
    ("5511987650002", "Rafael Lima", "rafael@example.com"),
    ("5521998760003", "Juliana Alves", "juliana@example.com"),
    ("5531976540004", "Pedro Henrique Souza", "pedro@example.com"),
    ("5541965430005", "Camila Ribeiro", "camila@example.com"),
]


def popular_demo(con: sqlite3.Connection, seed: int = 7, hoje: date | None = None) -> None:
    """Cria catálogo, clientes e pedidos fictícios com datas relativas a hoje."""
    if con.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]:
        return
    rnd = random.Random(seed)
    hoje = hoje or date.today()
    con.executemany("INSERT INTO produtos VALUES (?,?,?,?,?,?)", PRODUTOS)
    con.executemany("INSERT INTO clientes VALUES (?,?,?)", CLIENTES)

    # (dias atrás, status) — cobre os casos que um cliente costuma perguntar
    cenarios = [
        (1, "aguardando_pagamento"), (2, "pago"), (3, "em_separacao"), (5, "enviado"),
        (8, "enviado"), (6, "entregue"), (12, "entregue"), (25, "entregue"), (45, "entregue"), (20, "cancelado"),
    ]
    numero = 10480
    for i, (tel, _, _) in enumerate(CLIENTES):
        for dias, status in rnd.sample(cenarios, k=3 if i else 4):
            numero += rnd.randint(3, 40)
            compra = hoje - timedelta(days=dias)
            itens = [(sku, rnd.choice([1, 1, 1, 2]), preco)
                     for sku, _, _, preco, _, _ in rnd.sample(PRODUTOS, k=rnd.randint(1, 3))]
            total = sum(q * p for _, q, p in itens)
            rastreio = previsao = entrega = None
            if status in ("enviado", "entregue"):
                rastreio = f"AA{rnd.randint(100000000, 999999999)}BR"
                previsao = (compra + timedelta(days=7)).isoformat()
            if status == "entregue":
                entrega = (compra + timedelta(days=min(dias - 1, rnd.randint(3, 6)))).isoformat()
            if status in ("pago", "em_separacao"):
                previsao = (compra + timedelta(days=8)).isoformat()
            con.execute(
                "INSERT INTO pedidos VALUES (?,?,?,?,?,?,?,?,?)",
                (str(numero), tel, compra.isoformat(), status, round(total + 19.90, 2),
                 rnd.choice(["Pix", "Cartão de crédito 3x", "Boleto"]), rastreio, previsao, entrega))
            con.executemany("INSERT INTO itens_pedido VALUES (?,?,?,?)",
                            [(str(numero), sku, qtd, preco) for sku, qtd, preco in itens])
    con.commit()


# ------------------------------------------------------------------ conversas
def garantir_conversa(con: sqlite3.Connection, telefone: str, nome: str | None, canal: str) -> sqlite3.Row:
    con.execute(
        "INSERT INTO conversas (telefone, nome, status, canal, criado_em, atualizado_em) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(telefone) DO UPDATE SET atualizado_em = excluded.atualizado_em, "
        "nome = COALESCE(excluded.nome, conversas.nome)",
        (telefone, nome, "bot", canal, agora(), agora()))
    con.commit()
    return con.execute("SELECT * FROM conversas WHERE telefone = ?", (telefone,)).fetchone()


def salvar_mensagem(con: sqlite3.Connection, telefone: str, papel: str, conteudo: dict) -> None:
    con.execute("INSERT INTO mensagens (telefone, papel, conteudo, criado_em) VALUES (?,?,?,?)",
                (telefone, papel, json.dumps(conteudo, ensure_ascii=False), agora()))
    con.commit()


def carregar_historico(con: sqlite3.Connection, telefone: str, limite: int) -> list[dict]:
    """Últimas mensagens, sempre começando numa fala do cliente (nunca no meio de uma chamada de ferramenta)."""
    linhas = con.execute(
        "SELECT conteudo FROM mensagens WHERE telefone = ? ORDER BY id DESC LIMIT ?", (telefone, limite)).fetchall()
    msgs = [json.loads(r["conteudo"]) for r in reversed(linhas)]
    while msgs and not (msgs[0]["papel"] == "usuario"):
        msgs.pop(0)
    return msgs


def ja_recebida(con: sqlite3.Connection, id_externo: str) -> bool:
    """Idempotência: o WhatsApp reenvia webhooks quando não recebe 200 a tempo."""
    try:
        con.execute("INSERT INTO mensagens_recebidas VALUES (?, ?)", (id_externo, agora()))
        con.commit()
        return False
    except sqlite3.IntegrityError:
        return True
