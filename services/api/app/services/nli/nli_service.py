"""
NLI Service Orchestrator

Coordinates the five-stage RAG pipeline:
  1. IntentClassifier  — determine domains + graph flag
  2. VectorRetriever   — pgvector cosine search
  3. GraphTraverser    — Neo4j topology context (optional)
  4. ContextBuilder    — assemble prompt text
  5. ClaudeSynthesizer — generate and parse answer
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import NLIQuery, NLIResponse, NLISource
from app.services.nli.intent_classifier import IntentClassifier
from app.services.nli.vector_retriever import VectorRetriever
from app.services.nli.graph_traverser import GraphTraverser
from app.services.nli.context_builder import ContextBuilder
from app.services.nli.claude_synthesizer import ClaudeSynthesizer

logger = logging.getLogger(__name__)


class NLIService:
    """Orchestrates the five-stage NLI/RAG pipeline."""

    def __init__(self, api_key: str, model: str) -> None:
        self._classifier = IntentClassifier()
        self._retriever = VectorRetriever()
        self._traverser = GraphTraverser()
        self._builder = ContextBuilder()
        self._synthesizer = ClaudeSynthesizer(api_key=api_key, model=model)
        self.available = self._synthesizer.available

    async def query(
        self,
        db: AsyncSession,
        neo4j_client,
        question: str,
        org_id: str,
        top_k: int = 5,
    ) -> NLIResponse:
        # Stage 1 — intent classification
        intent = self._classifier.classify(question)
        logger.info(
            "NLI query: domains=%s needs_graph=%s",
            intent.domains,
            intent.needs_graph,
        )

        # Use the actual question embedding for retrieval
        from app.services.nli.intent_classifier import _get_model
        import numpy as np
        q_vec = _get_model().encode(question, convert_to_numpy=True)

        # Stage 2 — vector retrieval (parallel across domains)
        retrieval_tasks = [
            self._retriever.retrieve(
                db=db,
                org_id=org_id,
                domain=domain,
                query_vec=q_vec,
                top_k=top_k,
            )
            for domain in intent.domains
        ]
        domain_results = await asyncio.gather(*retrieval_tasks)

        # Deduplicate by device_id, keeping highest similarity
        seen: dict[str, object] = {}
        for list_of_devices in domain_results:
            for d in list_of_devices:
                if d.device_id not in seen or d.similarity > seen[d.device_id].similarity:
                    seen[d.device_id] = d
        all_devices = sorted(seen.values(), key=lambda d: d.similarity, reverse=True)

        # Stage 3 — graph traversal (optional)
        graph_context = None
        graph_used = False
        if intent.needs_graph and neo4j_client is not None:
            graph_context = await self._traverser.traverse(
                neo4j_client=neo4j_client,
                question=question,
                anchor_devices=all_devices[:3],
                extracted_entities=intent.extracted_entities,
            )
            graph_used = graph_context is not None

        # Stage 4 — context assembly
        context_text, sources = self._builder.build(all_devices, graph_context)

        # Stage 5 — Claude synthesis
        synthesis = await self._synthesizer.synthesize(
            question=question,
            context=context_text,
        )

        return NLIResponse(
            answer=synthesis.answer,
            sources=sources,
            confidence=synthesis.confidence,
            query_type=synthesis.query_type,
            retrieved_device_count=len(all_devices),
            graph_traversal_used=graph_used,
        )