"""
HyDE — Hypothetical Document Embeddings

Instead of embedding the raw query (which may be short and vague),
we ask the LLM to generate a hypothetical answer, then embed that.
The hypothesis is closer in semantic space to actual document chunks.

We use the AVERAGE of the original query embedding and the HyDE
embedding — this preserves the original intent while gaining
the richer vocabulary of the hypothetical answer.

Reference: Gao et al., "Precise Zero-Shot Dense Retrieval without
Relevance Labels" (2022)
"""

from __future__ import annotations

from anthropic import AsyncAnthropic
from nexus_core.config import get_settings
from nexus_core.logging import get_logger
from openai import AsyncOpenAI

logger = get_logger(__name__)
settings = get_settings()

_HYDE_SYSTEM = (
    "You are a helpful assistant. Given a question, write a short, "
    "factual paragraph (3-5 sentences) that directly answers it. "
    "Write as if you are a knowledgeable employee at the company. "
    "Do not hedge or say 'I don't know' — always write a plausible answer."
)


class HyDEExpander:
    def __init__(self) -> None:
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self._anthropic = (
            AsyncAnthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )

    async def expand(self, query: str) -> str:
        """
        Generate a hypothetical answer for the query.
        Returns the hypothesis text (not an embedding — caller embeds).
        """
        try:
            if self._anthropic:
                return await self._expand_anthropic(query)
            return await self._expand_openai(query)
        except Exception as e:
            logger.warning("hyde.expansion_failed", error=str(e))
            return query  # Fall back to original query

    async def _expand_anthropic(self, query: str) -> str:
        msg = await self._anthropic.messages.create(
            model="claude-haiku-4-5-20251001",  # Fast + cheap for expansion
            max_tokens=200,
            system=_HYDE_SYSTEM,
            messages=[{"role": "user", "content": query}],
        )
        return msg.content[0].text

    async def _expand_openai(self, query: str) -> str:
        resp = await self._openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            messages=[
                {"role": "system", "content": _HYDE_SYSTEM},
                {"role": "user", "content": query},
            ],
        )
        return resp.choices[0].message.content or query
