"""
NLI Context Builder

Serialises retrieved device and graph data into a token-budgeted prompt context block.
Truncation order (lowest priority first): change record details, graph edges, device metadata fields.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import tiktoken

from app.services.nli.vector_retriever import DeviceContext
from app.services.nli.graph_traverser import GraphContext, QueryShape
from app.api.schemas import NLISource

logger = logging.getLogger(__name__)

TOKEN_BUDGET = 8_000
_ENCODING = tiktoken.get_encoding("cl100k_base")


class ContextBuilder:
    """Converts retrieved device + graph data into a prompt-ready text block."""

    def _count_tokens(self, text: str) -> int:
        return len(_ENCODING.encode(text))

    def _format_device(self, d: DeviceContext, include_changes: bool = True) -> str:
        sp = d.metadata.get("security_posture", {})
        role = d.metadata.get("inferred_role", d.device_type or "unknown")
        confidence = d.metadata.get("role_confidence")
        role_str = f"{role} (confidence: {confidence:.0%})" if confidence else role

        lines = [
            f"Device: {d.hostname}",
            f"  Vendor: {d.vendor or 'unknown'} | Type: {d.device_type or 'unknown'} | Role: {role_str}",
        ]

        if sp:
            ssh = "enabled" if sp.get("ssh_enabled") else "disabled"
            telnet = "enabled" if sp.get("telnet_enabled") else "disabled"
            snmp = "enabled" if sp.get("snmp_enabled") else "disabled"
            http = "enabled" if sp.get("http_enabled") else "disabled"
            lines.append(f"  Security: SSH={ssh}, Telnet={telnet}, SNMP={snmp}, HTTP={http}")

        if d.compliance_scope:
            lines.append(f"  Compliance scope: {', '.join(d.compliance_scope)}")

        lines.append(f"  [Source: {d.device_type or 'device'} similarity={d.similarity:.2f}]")

        if include_changes and d.recent_changes:
            lines.append(f"  Recent changes ({len(d.recent_changes)}):")
            for c in d.recent_changes[:3]:
                lines.append(
                    f"    - {c['change_number']} | {c['status']} | {c.get('description', '')[:60]}"
                )

        if d.recent_alerts:
            lines.append(f"  Recent alerts ({len(d.recent_alerts)}):")
            for a in d.recent_alerts[:3]:
                lines.append(f"    - [{a['severity']}] {a['message'][:60]}")

        return "\n".join(lines)

    def _format_graph(self, graph: GraphContext, include_edges: bool = True) -> str:
        lines = ["\n=== TOPOLOGY ==="]
        if graph.path:
            lines.append("Path: " + " --> ".join(graph.path))
        for node in graph.nodes[:30]:
            hostname = node.get("hostname") or node.get("id", "?")
            lines.append(f"  Node: {hostname}")
        if include_edges:
            for edge in graph.edges[:20]:
                lines.append(
                    f"  {edge.get('start', '?')} --{edge.get('type', '?')}--> {edge.get('end', '?')}"
                )
        return "\n".join(lines)

    def build(
        self,
        devices: List[DeviceContext],
        graph: Optional[GraphContext],
    ) -> Tuple[str, List[NLISource]]:
        """
        Build prompt context from retrieved devices and optional graph context.

        Returns:
            (context_text, sources_list)
        """
        if not devices:
            return "No matching devices found in the network database.", []

        sources = [
            NLISource(
                device_id=d.device_id,
                hostname=d.hostname,
                similarity=d.similarity,
            )
            for d in devices
        ]

        # Build full context and check token budget
        device_block = "\n=== NETWORK CONTEXT ===\n"
        device_block += "\n\n".join(
            self._format_device(d, include_changes=True) for d in devices
        )

        graph_block = self._format_graph(graph, include_edges=True) if graph else ""
        full_context = device_block + graph_block

        if self._count_tokens(full_context) <= TOKEN_BUDGET:
            return full_context, sources

        # Truncation pass 1: drop change details
        device_block = "\n=== NETWORK CONTEXT ===\n"
        device_block += "\n\n".join(
            self._format_device(d, include_changes=False) for d in devices
        )
        graph_block = self._format_graph(graph, include_edges=True) if graph else ""
        full_context = device_block + graph_block

        if self._count_tokens(full_context) <= TOKEN_BUDGET:
            logger.debug("ContextBuilder: truncated change details to fit token budget")
            return full_context, sources

        # Truncation pass 2: drop graph edges
        graph_block = self._format_graph(graph, include_edges=False) if graph else ""
        full_context = device_block + graph_block

        if self._count_tokens(full_context) <= TOKEN_BUDGET:
            logger.debug("ContextBuilder: truncated graph edges to fit token budget")
            return full_context, sources

        # Truncation pass 3: trim to fewest devices that fit
        for n in range(len(devices) - 1, 0, -1):
            device_block = "\n=== NETWORK CONTEXT ===\n"
            device_block += "\n\n".join(
                self._format_device(d, include_changes=False) for d in devices[:n]
            )
            full_context = device_block
            if self._count_tokens(full_context) <= TOKEN_BUDGET:
                logger.warning(
                    "ContextBuilder: reduced to %d devices to fit token budget", n
                )
                return full_context, sources[:n]

        # Absolute fallback: first device only
        return self._format_device(devices[0], include_changes=False), sources[:1]