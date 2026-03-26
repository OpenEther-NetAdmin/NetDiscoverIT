"""
NLI Graph Traverser

Wraps Neo4jClient to provide three query shapes for topology context retrieval:
neighborhood (2-hop), path (shortestPath), and VLAN segmentation.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)

_PATH_PATTERN = re.compile(r"\b(path from|route from|trace from|hop from)\b", re.IGNORECASE)
_VLAN_PATTERN = re.compile(r"\b(vlan|segment|same network|broadcast domain)\b", re.IGNORECASE)


class QueryShape(str, Enum):
    NEIGHBORHOOD = "neighborhood"
    PATH = "path"
    VLAN = "vlan"


@dataclass
class GraphContext:
    nodes: List[dict] = field(default_factory=list)
    edges: List[dict] = field(default_factory=list)
    path: Optional[List[str]] = None
    query_shape: str = QueryShape.NEIGHBORHOOD


class GraphTraverser:
    """Executes topology queries against Neo4j for NLI context enrichment."""

    def _detect_shape(self, question: str) -> QueryShape:
        if _PATH_PATTERN.search(question):
            return QueryShape.PATH
        if _VLAN_PATTERN.search(question):
            return QueryShape.VLAN
        return QueryShape.NEIGHBORHOOD

    def _pick_anchor(self, anchor_devices, extracted_entities: list[str]) -> Optional[str]:
        """Return hostname of the best anchor device."""
        if not anchor_devices:
            return None
        # Try to match an extracted entity to a device hostname
        for entity in extracted_entities:
            for device in anchor_devices:
                if entity.lower() in device.hostname.lower():
                    return device.hostname
        # Fall back to highest-similarity device
        return anchor_devices[0].hostname

    async def traverse(
        self,
        neo4j_client,
        question: str,
        anchor_devices,
        extracted_entities: list[str] | None = None,
    ) -> Optional[GraphContext]:
        """Run a graph query. Returns None if Neo4j is unavailable or the query fails."""
        if neo4j_client is None:
            return None

        shape = self._detect_shape(question)
        entities = extracted_entities or []
        anchor = self._pick_anchor(anchor_devices, entities)
        if not anchor:
            return None

        try:
            if shape == QueryShape.PATH:
                return await self._run_path_query(neo4j_client, anchor, entities)
            elif shape == QueryShape.VLAN:
                return await self._run_vlan_query(neo4j_client, anchor)
            else:
                return await self._run_neighborhood_query(neo4j_client, anchor)
        except Exception:
            logger.warning("GraphTraverser: query failed (Neo4j unavailable?)", exc_info=True)
            return None

    async def _run_neighborhood_query(self, client, anchor: str) -> GraphContext:
        """2-hop neighborhood from anchor device."""
        async with client._driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Device {hostname: $hostname})-[r*1..2]-(neighbor)
                RETURN d, r, neighbor
                LIMIT 50
                """,
                {"hostname": anchor},
            )
            records = await result.data()

        nodes = []
        edges = []
        seen_nodes: set[str] = set()
        for record in records:
            for key in ("d", "neighbor"):
                node = dict(record.get(key, {}))
                node_id = node.get("id") or node.get("hostname", "")
                if node_id and node_id not in seen_nodes:
                    nodes.append(node)
                    seen_nodes.add(node_id)
            for rel in record.get("r", []):
                edges.append({
                    "type": rel.type if hasattr(rel, "type") else str(rel),
                    "start": rel.start_node.get("hostname", "") if hasattr(rel, "start_node") else "",
                    "end": rel.end_node.get("hostname", "") if hasattr(rel, "end_node") else "",
                })
        return GraphContext(nodes=nodes, edges=edges, query_shape=QueryShape.NEIGHBORHOOD)

    async def _run_path_query(
        self, client, anchor: str, entities: list[str]
    ) -> GraphContext:
        """shortestPath between two devices."""
        # Try to find a second device in extracted entities
        target = next(
            (e for e in entities if e.lower() != anchor.lower()), None
        )
        if not target:
            # Fall back to neighborhood if we can't find a target
            return await self._run_neighborhood_query(client, anchor)

        async with client._driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Device {hostname: $from}), (b:Device {hostname: $to}),
                      p = shortestPath((a)-[*]-(b))
                RETURN [node in nodes(p) | node.hostname] AS path_hostnames
                """,
                {"from": anchor, "to": target},
            )
            records = await result.data()

        path = records[0]["path_hostnames"] if records else []
        return GraphContext(path=path, query_shape=QueryShape.PATH)

    async def _run_vlan_query(self, client, anchor: str) -> GraphContext:
        """Find devices in the same VLAN as anchor."""
        async with client._driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Device {hostname: $hostname})-[:HAS_INTERFACE]->(:Interface)
                      -[:MEMBER_OF]->(v:VLAN)<-[:MEMBER_OF]-(:Interface)
                      <-[:HAS_INTERFACE]-(peer:Device)
                RETURN d, v, peer
                LIMIT 50
                """,
                {"hostname": anchor},
            )
            records = await result.data()

        nodes = []
        seen: set[str] = set()
        for record in records:
            for key in ("d", "peer"):
                node = dict(record.get(key, {}))
                h = node.get("hostname", "")
                if h and h not in seen:
                    nodes.append(node)
                    seen.add(h)
        return GraphContext(nodes=nodes, query_shape=QueryShape.VLAN)