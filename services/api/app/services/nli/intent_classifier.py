"""
NLI Intent Classifier

Embeds the user question and computes cosine similarity against precomputed domain
centroid vectors to route the query to the correct pgvector column(s). A separate
regex scan detects topology keywords and sets the needs_graph flag.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Model shared across all instances — loaded once at process startup
_MODEL: SentenceTransformer | None = None
MODEL_NAME = "all-mpnet-base-v2"

# Similarity threshold: domains above this score are selected
SIMILARITY_THRESHOLD = 0.30

# Topology keywords that trigger Neo4j graph traversal
_TOPOLOGY_PATTERN = re.compile(
    r"\b(connects?|connected|path|neighbor|upstream|downstream|hop|reach|next.hop|"
    r"adjacent|topology|link|interface|gateway|route.to)\b",
    re.IGNORECASE,
)

# Entity extraction: IPv4 addresses and kebab/dot hostnames
_IP_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_HOSTNAME_PATTERN = re.compile(r"\b[a-zA-Z][a-zA-Z0-9]*(?:[-\.][a-zA-Z0-9]+){1,}\b")

# Seed phrases per domain — centroids are computed from these at init time
_DOMAIN_SEEDS: dict[str, list[str]] = {
    "inventory": [
        "list all routers",
        "how many devices",
        "what vendor is this device",
        "device type",
        "what kind of switch",
        "show all network devices",
    ],
    "topology": [
        "what connects to this device",
        "path from host to firewall",
        "neighbors of core router",
        "upstream device",
        "directly connected interfaces",
        "network topology",
    ],
    "security": [
        "telnet enabled devices",
        "SSH is disabled",
        "open ports on device",
        "security posture",
        "SNMP community string configured",
        "which devices have HTTP enabled",
    ],
    "compliance": [
        "PCI scope devices",
        "HIPAA tagged network equipment",
        "compliance devices list",
        "in scope for audit",
        "compliance boundary devices",
        "SOC2 in scope",
    ],
    "changes": [
        "what changed last week",
        "recent configuration modifications",
        "change record for device",
        "configuration drift detected",
        "modified configuration",
        "unapproved changes",
    ],
}


@dataclass
class QueryIntent:
    domains: List[str]             # e.g. ["topology", "security"]
    needs_graph: bool
    extracted_entities: List[str]  # hostnames and IPs found in the question


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        logger.info("Loading sentence-transformers model: %s", MODEL_NAME)
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    # Ensure 1D arrays for dot product
    a = a.flatten()
    b = b.flatten()
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class IntentClassifier:
    """Classifies a natural-language question into one or more retrieval domains."""

    def __init__(self) -> None:
        model = _get_model()
        # Precompute domain centroids from seed phrases
        self._centroids: dict[str, np.ndarray] = {}
        for domain, seeds in _DOMAIN_SEEDS.items():
            embeddings = model.encode(seeds, convert_to_numpy=True)
            if isinstance(embeddings, list):
                embeddings = np.array(embeddings)
            self._centroids[domain] = embeddings.mean(axis=0).flatten()

    def classify(self, question: str) -> QueryIntent:
        model = _get_model()
        q_vec = model.encode(question, convert_to_numpy=True)
        if isinstance(q_vec, list):
            q_vec = np.array(q_vec)
        q_vec = q_vec.flatten()

        # Compute similarity to each domain centroid
        scores = {
            domain: _cosine_similarity(q_vec, centroid)
            for domain, centroid in self._centroids.items()
        }

        selected = [d for d, s in scores.items() if s >= SIMILARITY_THRESHOLD]

        # Fallback: ambiguous question → search all domains
        if not selected:
            selected = list(_DOMAIN_SEEDS.keys())
            logger.debug("No domain cleared threshold — using all domains. Scores: %s", scores)

        needs_graph = bool(_TOPOLOGY_PATTERN.search(question))

        # Extract entities (IPs + hostnames) from the question
        entities: list[str] = _IP_PATTERN.findall(question)
        for match in _HOSTNAME_PATTERN.finditer(question):
            token = match.group()
            # Filter out common English words that match the hostname pattern
            if len(token) > 4 and "-" in token or "." in token:
                entities.append(token)

        return QueryIntent(
            domains=selected,
            needs_graph=needs_graph,
            extracted_entities=entities,
        )