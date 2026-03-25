"""
ContainerLab topology generator service.
Generates ContainerLab YAML topology from Neo4j topology data.
"""

from typing import Dict, Any, List
from app.db.neo4j import get_neo4j_client


class TopologyGenerator:
    """Service for generating ContainerLab topology from Neo4j"""

    async def generate_topology(
        self,
        organization_id: str,
        device_ids: List[str],
        proposed_configs: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Generate ContainerLab topology YAML from Neo4j data.

        Args:
            organization_id: Organization UUID
            device_ids: List of device UUIDs to include
            proposed_configs: Dict of device_id -> proposed config

        Returns:
            Dict with topology_yaml, nodes, links
        """
        neo4j = await get_neo4j_client()

        nodes = []
        links = []

        for device_id in device_ids:
            device_result = await neo4j.execute_query(
                """
                MATCH (d:Device {id: $device_id})
                RETURN d.hostname as hostname, d.management_ip as mgmt_ip,
                       d.device_type as device_type, d.vendor as vendor
                """,
                {"device_id": device_id},
            )

            if device_result:
                record = device_result[0]
                nodes.append(
                    {
                        "id": device_id,
                        "hostname": record.get("hostname", f"device-{device_id[:8]}"),
                        "mgmt_ip": record.get("mgmt_ip"),
                        "device_type": record.get("device_type", "linux"),
                        "vendor": record.get("vendor", "generic"),
                        "config": proposed_configs.get(device_id, ""),
                    }
                )

        links_result = await neo4j.execute_query(
            """
            MATCH (d1:Device)-[r:CONNECTED_TO]->(d2:Device)
            WHERE d1.id IN $device_ids AND d2.id IN $device_ids
            RETURN d1.id as source, d2.id as target, r.interface as interface
            """,
            {"device_ids": device_ids},
        )

        for link in links_result:
            links.append(
                {
                    "source": link.get("source"),
                    "target": link.get("target"),
                    "interface": link.get("interface"),
                }
            )

        topology_yaml = self._generate_clab_yaml(nodes, links)

        return {
            "topology_yaml": topology_yaml,
            "nodes": nodes,
            "links": links,
            "node_count": len(nodes),
            "link_count": len(links),
        }

    def _generate_clab_yaml(self, nodes: List[Dict], links: List[Dict]) -> str:
        """Generate ContainerLab topology YAML"""
        lines = [
            "name: simulation-topology",
            "",
            "topology:",
            "  nodes:",
        ]

        for node in nodes:
            node_name = node["hostname"].replace("-", "_")
            device_type = node.get("device_type", "linux")

            if device_type in ["router", "switch"]:
                kind = "linux"
            else:
                kind = "linux"

            lines.append(f"    {node_name}:")
            lines.append(f"      kind: {kind}")
            if node.get("mgmt_ip"):
                lines.append(f"      mgmt-ip: {node['mgmt_ip']}")

        lines.append("  links:")
        for link in links:
            source_name = next(
                (
                    n["hostname"].replace("-", "_")
                    for n in nodes
                    if n["id"] == link["source"]
                ),
                "node1",
            )
            target_name = next(
                (
                    n["hostname"].replace("-", "_")
                    for n in nodes
                    if n["id"] == link["target"]
                ),
                "node2",
            )
            lines.append(
                f"    - endpoints: [{source_name}:{link.get('interface', 'eth0')},{target_name}:{link.get('interface', 'eth0')}]"
            )

        return "\n".join(lines)


topology_generator = TopologyGenerator()
