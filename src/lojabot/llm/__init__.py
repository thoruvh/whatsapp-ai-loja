"""Seleção do provedor de IA pela configuração."""
from __future__ import annotations

from lojabot.config import Config
from lojabot.llm.base import Chamada, ProvedorLLM, RespostaLLM

__all__ = ["Chamada", "ProvedorLLM", "RespostaLLM", "criar_provedor"]


def criar_provedor(cfg: Config) -> ProvedorLLM:
    if cfg.llm_provedor == "anthropic":
        from lojabot.llm.anthropic_llm import ProvedorAnthropic

        if not cfg.anthropic_api_key:
            raise RuntimeError("Defina ANTHROPIC_API_KEY para usar LLM_PROVEDOR=anthropic")
        return ProvedorAnthropic(cfg.anthropic_api_key, cfg.modelo)
    if cfg.llm_provedor == "openai":
        from lojabot.llm.openai_llm import ProvedorOpenAI

        if not cfg.openai_api_key:
            raise RuntimeError("Defina OPENAI_API_KEY para usar LLM_PROVEDOR=openai")
        return ProvedorOpenAI(cfg.openai_api_key, cfg.modelo)
    if cfg.llm_provedor == "demo":
        from lojabot.llm.demo_llm import ProvedorDemo

        return ProvedorDemo(cfg.nome_loja)
    raise ValueError(f"LLM_PROVEDOR inválido: {cfg.llm_provedor!r} (use anthropic, openai ou demo)")
