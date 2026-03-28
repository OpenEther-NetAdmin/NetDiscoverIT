"""
Neo4j Graph Database Client
Based on net-discit database-schemas.md
"""

import logging
from typing import List, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Fail fast if the neo4j driver is not installed — do not allow silent failures
try:
    from neo4j import AsyncGraphDatabase
except ImportError as exc:
    raise ImportError(
        "neo4j Python driver is required but not installed. " "Run: pip install neo4j"
    ) from exc


class Neo4jClient:
    """Neo4j client for network topology graph"""

    # Connection timeout in seconds
    CONNECTION_TIMEOUT = 10.0

    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self._driver = None

    async def connect(self):
        """Connect to Neo4j"""
        self._driver = AsyncGraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
            connection_timeout=self.CONNECTION_TIMEOUT,
        )
        await self._driver.verify_connectivity()
        logger.info("Connected to Neo4j")

    async def close(self):
        """Close connection"""
        if self._driver:
            await self._driver.close()

    async def create_device_node(self, device: Dict) -> Dict:
        """Create or update a Device node"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MERGE (d:Device {id: $id})
        SET d.hostname = $hostname,
            d.ip_address = $ip_address,
            d.mac_address = $mac_address,
            d.vendor = $vendor,
            d.model = $model,
            d.os_type = $os_type,
            d.os_version = $os_version,
            d.device_type = $device_type,
            d.device_role = $device_role,
            d.serial_number = $serial_number,
            d.location = $location,
            d.organization_id = $organization_id,
            d.last_seen = datetime()
        RETURN d
        """

        async with self._driver.session() as session:
            result = await session.run(
                query,
                {
                    "id": str(device.get("id", uuid4())),
                    "hostname": device.get("hostname"),
                    "ip_address": str(device.get("ip_address", "")),
                    "mac_address": device.get("mac_address"),
                    "vendor": device.get("vendor"),
                    "model": device.get("model"),
                    "os_type": device.get("os_type"),
                    "os_version": device.get("os_version"),
                    "device_type": device.get("device_type"),
                    "device_role": device.get("device_role"),
                    "serial_number": device.get("serial_number"),
                    "location": device.get("location"),
                    "organization_id": str(device.get("organization_id", "")),
                },
            )
            record = await result.single(strict=False)
            return dict(record["d"]) if record else {}

    async def create_interface_node(self, interface: Dict) -> Dict:
        """Create or update an Interface node"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MERGE (i:Interface {id: $id})
        SET i.name = $name,
            i.description = $description,
            i.mac_address = $mac_address,
            i.ip_address = $ip_address,
            i.subnet_mask = $subnet_mask,
            i.status = $status,
            i.admin_status = $admin_status,
            i.speed = $speed,
            i.duplex = $duplex,
            i.mtu = $mtu,
            i.vlan_id = $vlan_id,
            i.last_seen = datetime()
        RETURN i
        """

        async with self._driver.session() as session:
            result = await session.run(
                query,
                {
                    "id": str(interface.get("id", uuid4())),
                    "name": interface.get("name"),
                    "description": interface.get("description"),
                    "mac_address": interface.get("mac_address"),
                    "ip_address": str(interface.get("ip_address", "")),
                    "subnet_mask": str(interface.get("subnet_mask", "")),
                    "status": interface.get("status"),
                    "admin_status": interface.get("admin_status"),
                    "speed": interface.get("speed"),
                    "duplex": interface.get("duplex"),
                    "mtu": interface.get("mtu"),
                    "vlan_id": interface.get("vlan_id"),
                },
            )
            record = await result.single(strict=False)
            return dict(record["i"]) if record else {}

    async def create_has_interface_relationship(
        self, device_id: str, interface_id: str, slot: str = None
    ) -> bool:
        """Create HAS_INTERFACE relationship"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MATCH (d:Device {id: $device_id})
        MATCH (i:Interface {id: $interface_id})
        MERGE (d)-[r:HAS_INTERFACE]->(i)
        SET r.slot = $slot,
            r.discovered_at = datetime()
        RETURN r
        """

        async with self._driver.session() as session:
            await session.run(
                query,
                {"device_id": device_id, "interface_id": interface_id, "slot": slot},
            )
            return True

    async def create_connected_to_relationship(
        self,
        interface1_id: str,
        interface2_id: str,
        discovery_method: str = None,
        link_speed: int = None,
        link_status: str = None,
    ) -> bool:
        """Create bidirectional CONNECTED_TO relationship"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MATCH (i1:Interface {id: $interface1_id})
        MATCH (i2:Interface {id: $interface2_id})
        MERGE (i1)-[r1:CONNECTED_TO]->(i2)
        SET r1.discovery_method = $discovery_method,
            r1.link_speed = $link_speed,
            r1.link_status = $link_status,
            r1.discovered_at = datetime()
        MERGE (i2)-[r2:CONNECTED_TO]->(i1)
        SET r2.discovery_method = $discovery_method,
            r2.link_speed = $link_speed,
            r2.link_status = $link_status,
            r2.discovered_at = datetime()
        RETURN r1, r2
        """

        async with self._driver.session() as session:
            await session.run(
                query,
                {
                    "interface1_id": interface1_id,
                    "interface2_id": interface2_id,
                    "discovery_method": discovery_method,
                    "link_speed": link_speed,
                    "link_status": link_status,
                },
            )
            return True

    async def create_vlan_node(self, vlan: Dict) -> Dict:
        """Create or update a VLAN node"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MERGE (v:VLAN {id: $id})
        SET v.vlan_id = $vlan_id,
            v.name = $name,
            v.description = $description,
            v.subnet = $subnet,
            v.gateway = $gateway,
            v.organization_id = $organization_id,
            v.discovered_at = datetime()
        RETURN v
        """

        async with self._driver.session() as session:
            result = await session.run(
                query,
                {
                    "id": str(vlan.get("id", uuid4())),
                    "vlan_id": vlan.get("vlan_id"),
                    "name": vlan.get("name"),
                    "description": vlan.get("description"),
                    "subnet": vlan.get("subnet"),
                    "gateway": vlan.get("gateway"),
                    "organization_id": str(vlan.get("organization_id", "")),
                },
            )
            record = await result.single(strict=False)
            return dict(record["v"]) if record else {}

    async def create_member_of_relationship(
        self,
        interface_id: str,
        vlan_id: int,
        mode: str = "access",
        native: bool = False,
    ) -> bool:
        """Create MEMBER_OF relationship"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MATCH (i:Interface {id: $interface_id})
        MATCH (v:VLAN {vlan_id: $vlan_id})
        MERGE (i)-[r:MEMBER_OF]->(v)
        SET r.mode = $mode,
            r.native = $native,
            r.discovered_at = datetime()
        RETURN r
        """

        async with self._driver.session() as session:
            await session.run(
                query,
                {
                    "interface_id": interface_id,
                    "vlan_id": vlan_id,
                    "mode": mode,
                    "native": native,
                },
            )
            return True

    async def find_path(self, source_hostname: str, dest_hostname: str) -> List[Dict]:
        """Find shortest path between two devices"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MATCH path = shortestPath(
            (d1:Device {hostname: $source})-[*]-(d2:Device {hostname: $dest})
        )
        RETURN path
        LIMIT 1
        """

        async with self._driver.session() as session:
            result = await session.run(
                query, {"source": source_hostname, "dest": dest_hostname}
            )
            record = await result.single(strict=False)
            if record:
                return [dict(n) for n in record["path"].nodes]
        return []

    async def find_devices_in_vlan(
        self, vlan_id: int, organization_id: str
    ) -> List[Dict]:
        """Find all devices in a VLAN"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MATCH (d:Device {organization_id: $org_id})
        -[:HAS_INTERFACE]->(i:Interface)-[:MEMBER_OF]->(v:VLAN {vlan_id: $vlan_id})
        RETURN DISTINCT d.hostname as hostname, d.ip_address as ip_address, d.device_type as device_type
        """

        async with self._driver.session() as session:
            result = await session.run(
                query, {"org_id": organization_id, "vlan_id": vlan_id}
            )
            return [dict(record) async for record in result]

    async def find_single_points_of_failure(self, organization_id: str) -> List[Dict]:
        """Find devices with only one connection"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MATCH (d:Device {organization_id: $org_id})
        OPTIONAL MATCH (d)-[:HAS_INTERFACE]->(i:Interface)-[c:CONNECTED_TO]-()
        WITH d, COUNT(DISTINCT c) as connection_count
        WHERE connection_count = 1
        RETURN d.hostname, d.ip_address, connection_count
        ORDER BY d.hostname
        """

        async with self._driver.session() as session:
            result = await session.run(query, {"org_id": organization_id})
            return [dict(record) async for record in result]

    async def get_topology(self, organization_id: str) -> Dict:
        """Get full topology for an organization"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MATCH (d:Device {organization_id: $org_id})
        OPTIONAL MATCH (d)-[:HAS_INTERFACE]->(i:Interface)
        OPTIONAL MATCH (i)-[c:CONNECTED_TO]->(i2:Interface)
        OPTIONAL MATCH (i2)<-[:HAS_INTERFACE]-(d2:Device)
        OPTIONAL MATCH (i)-[:MEMBER_OF]->(v:VLAN)
        RETURN d, i, c, i2, d2, v
        """

        nodes = []
        edges = []
        seen_node_ids = set()

        async with self._driver.session() as session:
            result = await session.run(query, {"org_id": organization_id})
            async for record in result:
                d_node = record["d"]
                i_node = record["i"]
                c_rel = record["c"]
                i2_node = record["i2"]
                d2_node = record["d2"]

                if d_node:
                    d_data = dict(d_node)
                    if d_data["id"] not in seen_node_ids:
                        nodes.append({"type": "device", **d_data})
                        seen_node_ids.add(d_data["id"])

                if i_node:
                    i_data = dict(i_node)
                    if i_data["id"] not in seen_node_ids:
                        nodes.append({"type": "interface", **i_data})
                        seen_node_ids.add(i_data["id"])

                    if i2_node and c_rel:
                        i2_data = dict(i2_node)
                        if i2_data["id"] not in seen_node_ids:
                            nodes.append({"type": "interface", **i2_data})
                            seen_node_ids.add(i2_data["id"])
                        edges.append(
                            {
                                "source": i_data["id"],
                                "target": i2_data["id"],
                                **dict(c_rel),
                            }
                        )

                if d2_node:
                    d2_data = dict(d2_node)
                    if d2_data["id"] not in seen_node_ids:
                        nodes.append({"type": "device", **d2_data})
                        seen_node_ids.add(d2_data["id"])

        return {"nodes": nodes, "edges": edges}

    async def get_device_connections(self, organization_id: str) -> list[dict]:
        """Return device-to-device connections for an org as {source, target} dicts.

        Collapses interface-level CONNECTED_TO edges to device-level pairs.
        Deduplicates by requiring d1.id < d2.id so each pair appears once.
        Returns an empty list if the driver is not connected.
        """
        if not self._driver:
            return []

        cypher = (
            "MATCH (d1:Device {organization_id: $org_id})"
            "-[:HAS_INTERFACE]->(:Interface)-[:CONNECTED_TO]->"
            "(:Interface)<-[:HAS_INTERFACE]-(d2:Device) "
            "WHERE d2.organization_id = $org_id AND d1.id < d2.id "
            "RETURN DISTINCT d1.id AS source, d2.id AS target"
        )
        edges = []
        async with self._driver.session() as session:
            result = await session.run(cypher, {"org_id": organization_id})
            async for record in result:
                edges.append(
                    {"source": str(record["source"]), "target": str(record["target"])}
                )
        return edges

    async def delete_orphaned_interfaces(self) -> int:
        """Clean up orphaned interface nodes"""
        if not self._driver:
            raise RuntimeError("Neo4j client is not connected")

        query = """
        MATCH (i:Interface)
        WHERE NOT (i)<-[:HAS_INTERFACE]-(:Device)
        DETACH DELETE i
        RETURN count(i) as deleted
        """

        async with self._driver.session() as session:
            result = await session.run(query)
            record = await result.single(strict=False)
            return record["deleted"] if record else 0

    async def create_constraints(self):
        """Create uniqueness constraints and indexes"""
        constraints = [
            "CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT interface_id_unique IF NOT EXISTS FOR (i:Interface) REQUIRE i.id IS UNIQUE",
            "CREATE INDEX device_ip_index IF NOT EXISTS FOR (d:Device) ON (d.ip_address)",
            "CREATE INDEX device_hostname_index IF NOT EXISTS FOR (d:Device) ON (d.hostname)",
            "CREATE INDEX interface_ip_index IF NOT EXISTS FOR (i:Interface) ON (i.ip_address)",
            "CREATE INDEX vlan_id_index IF NOT EXISTS FOR (v:VLAN) ON (v.vlan_id)",
        ]

        async with self._driver.session() as session:
            for constraint in constraints:
                try:
                    await session.run(constraint)
                except Exception as e:
                    logger.debug(f"Constraint creation: {e}")


# Singleton instance
_neo4j_client: Optional[Neo4jClient] = None


async def get_neo4j_client() -> Neo4jClient:
    """Get Neo4j client instance"""
    global _neo4j_client
    if _neo4j_client is None:
        from app.core.config import settings

        _neo4j_client = Neo4jClient(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
        )
        await _neo4j_client.connect()
    return _neo4j_client


async def close_neo4j_client():
    """Close the Neo4j singleton and release resources"""
    global _neo4j_client
    if _neo4j_client:
        await _neo4j_client.close()
        _neo4j_client = None
