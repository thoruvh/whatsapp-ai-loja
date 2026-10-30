"""Configuração via variáveis de ambiente (veja .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _carregar_dotenv(caminho: Path = Path(".env")) -> None:
    """Leitor mínimo de .env para não exigir dependência extra."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_dotenv()


def _env(nome: str, padrao: str = "") -> str:
    return os.environ.get(nome, padrao)


@dataclass
class Config:
    nome_loja: str = field(default_factory=lambda: _env("NOME_LOJA", "Casa Aurora"))
    banco: str = field(default_factory=lambda: _env("BANCO", "data/lojabot.db"))

    # IA: "anthropic", "openai" ou "demo" (regras simples, sem IA, para testes e demonstração offline)
    llm_provedor: str = field(default_factory=lambda: _env("LLM_PROVEDOR", "demo"))
    llm_modelo: str = field(default_factory=lambda: _env("LLM_MODELO", ""))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    historico_max: int = field(default_factory=lambda: int(_env("HISTORICO_MAX", "20")))

    # Canal de envio: "meta", "evolution" ou "nenhum" (só simulador)
    canal: str = field(default_factory=lambda: _env("CANAL", "nenhum"))

    # WhatsApp Cloud API (Meta)
    meta_token: str = field(default_factory=lambda: _env("META_TOKEN"))
    meta_phone_number_id: str = field(default_factory=lambda: _env("META_PHONE_NUMBER_ID"))
    meta_app_secret: str = field(default_factory=lambda: _env("META_APP_SECRET"))
    meta_verify_token: str = field(default_factory=lambda: _env("META_VERIFY_TOKEN"))
    meta_api_versao: str = field(default_factory=lambda: _env("META_API_VERSAO", "v21.0"))

    # Evolution API
    evolution_url: str = field(default_factory=lambda: _env("EVOLUTION_URL"))
    evolution_api_key: str = field(default_factory=lambda: _env("EVOLUTION_API_KEY"))
    evolution_instancia: str = field(default_factory=lambda: _env("EVOLUTION_INSTANCIA"))
    evolution_webhook_token: str = field(default_factory=lambda: _env("EVOLUTION_WEBHOOK_TOKEN"))

    # Painel administrativo
    admin_token: str = field(default_factory=lambda: _env("ADMIN_TOKEN", "troque-este-token"))

    @property
    def modelo(self) -> str:
        if self.llm_modelo:
            return self.llm_modelo
        return {"anthropic": "claude-haiku-5-5", "openai": "gpt-4.1-mini"}.get(self.llm_provedor, "demo")


def carregar() -> Config:
    return Config()
