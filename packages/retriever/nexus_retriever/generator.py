"""
Generator — LLM answer generation with citations.

Supports:
  - Anthropic Claude (primary)
  - OpenAI GPT-4o (fallback)
  - Streaming via async generators (SSE)
  - Structured citation extraction
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import Any

from nexus_core.config import get_settings
from nexus_core.logging import get_logger
from nexus_core.schemas.domain import Citation, QueryResponse

logger = get_logger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = """\
You are a knowledgeable assistant for {company_name}.
Answer questions using ONLY the provided context from the company's connected tools.

Rules:
1. For every factual claim, cite the source using inline numbers like [1], [2].
2. You may cite the same source multiple times.
3. If the answer is not in the provided context, say exactly:
   "I don't have information on that in your connected sources."
4. Never fabricate information. Never use knowledge outside the context.
5. Be concise and direct. Use bullet points for lists.

Context:
{context}
"""


class Generator:
    def __init__(self) -> None:
        self._model = settings.generation_model

    async def generate(
        self,
        query: str,
        context: str,
        citation_metadata: list[dict[str, Any]],
        company_name: str = "your company",
        stream: bool = False,
    ) -> QueryResponse:
        """
        Generate a grounded answer. Returns a complete QueryResponse.
        For streaming, use generate_stream() instead.
        """
        system = _SYSTEM_PROMPT.format(
            company_name=company_name,
            context=context,
        )
        answer = await self._call_llm(system, query)
        citations = self._extract_citations(answer, citation_metadata)

        return QueryResponse(
            answer=answer,
            citations=citations,
            latency_ms=0,  # Set by caller
            cached=False,
        )

    async def generate_stream(
        self,
        query: str,
        context: str,
        citation_metadata: list[dict[str, Any]],
        company_name: str = "your company",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Streaming generator — yields SSE-compatible dicts.
        Caller formats these as Server-Sent Events.
        """
        system = _SYSTEM_PROMPT.format(
            company_name=company_name,
            context=context,
        )

        full_answer = ""
        async for token in self._stream_llm(system, query):
            full_answer += token
            yield {"type": "token", "content": token}

        citations = self._extract_citations(full_answer, citation_metadata)
        yield {"type": "citations", "citations": [c.model_dump(mode="json") for c in citations]}
        yield {"type": "done"}

    async def _call_llm(self, system: str, query: str) -> str:
        if settings.anthropic_api_key and "claude" in self._model:
            return await self._call_anthropic(system, query)
        return await self._call_openai(system, query)

    async def _call_anthropic(self, system: str, query: str) -> str:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": query}],
        )
        return msg.content[0].text

    async def _call_openai(self, system: str, query: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1500,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
        )
        return resp.choices[0].message.content or ""

    async def _stream_llm(self, system: str, query: str) -> AsyncGenerator[str, None]:
        if settings.anthropic_api_key and "claude" in self._model:
            async for token in self._stream_anthropic(system, query):
                yield token
        else:
            async for token in self._stream_openai(system, query):
                yield token

    async def _stream_anthropic(self, system: str, query: str) -> AsyncGenerator[str, None]:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        async with client.messages.stream(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": query}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def _stream_openai(self, system: str, query: str) -> AsyncGenerator[str, None]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        stream = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1500,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def _extract_citations(
        self,
        answer: str,
        citation_metadata: list[dict[str, Any]],
    ) -> list[Citation]:
        """
        Find all [N] references in the answer and map them to citation metadata.
        Returns only citations actually referenced in the answer.
        """
        referenced = set(int(m) for m in re.findall(r"\[(\d+)\]", answer))
        citations: list[Citation] = []

        for meta in citation_metadata:
            num = meta["number"]
            if num not in referenced:
                continue
            citations.append(
                Citation(
                    number=num,
                    title=meta.get("title"),
                    connector=meta.get("connector", ""),
                    source_url=meta.get("source_url"),
                    excerpt=meta.get("excerpt", "")[:300],
                    author_email=meta.get("author_email"),
                    modified_at=meta.get("modified_at"),
                )
            )

        return sorted(citations, key=lambda c: c.number)
