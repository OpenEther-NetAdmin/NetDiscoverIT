"""
Role Classification Service
Hybrid rule-based + ML classifier for network device roles
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

DEVICE_ROLES = [
    "core_router",
    "edge_router", 
    "distribution_switch",
    "access_switch",
    "spine_switch",
    "leaf_switch",
    "l2_firewall",
    "l3_firewall",
    "load_balancer",
    "server",
    "wireless_controller",
    "access_point",
    "gateway",
    "datacenter_switch",
    "endpoint_protection",
    "vpn_concentrator",
    "waf",
    "domain_controller",
    "unknown",
]

ROLE_RULES = {
    # Rules require device_type match as a prerequisite to avoid false positives
    # All rules assume device_type is already checked or is a strong indicator
    
    "core_router": [
        # Strong: BGP + multiple L3 interfaces (classic core router signature)
        lambda m: m.get("has_bgp", False) and m.get("l3_interface_count", 0) >= 3,
        # Moderate: OSPFs with high interface count and distribution characteristics
        lambda m: m.get("has_ospf", False) and m.get("l3_interface_count", 0) >= 4 and m.get("vlan_count", 0) >= 10,
    ],
    "edge_router": [
        # Strong: NAT + static routes (classic WAN edge)
        lambda m: m.get("nat_enabled", False) and m.get("has_static_routes", False),
        # Moderate: VPN + NAT (remote access edge)
        lambda m: m.get("vpn_enabled", False) and m.get("nat_enabled", False),
    ],
    "distribution_switch": [
        # Strong: Multiple VLANs + L3 interfaces (distribution layer)
        lambda m: m.get("vlan_count", 0) >= 10 and m.get("l3_interface_count", 0) >= 2,
        # Moderate: High port count + routing protocols but not core
        lambda m: m.get("interface_count", 0) >= 24 and m.get("has_ospf", False) and m.get("l3_interface_count", 0) < 4,
    ],
    "access_switch": [
        # Strong: PoE + high port count (typical access switch)
        lambda m: m.get("has_poe", False) and m.get("interface_count", 0) >= 24,
        # Moderate: VLANs but no routing (L2-only access)
        lambda m: m.get("vlan_count", 0) >= 3 and not m.get("has_bgp", False) and not m.get("has_ospf", False),
    ],
    "spine_switch": [
        # Strong: Arista + VXLAN (modern DC fabric)
        lambda m: m.get("vendor") in ["Arista"] and m.get("l3_interface_count", 0) >= 4,
        # Moderate: Cisco high-port with no routing (DC spine)
        lambda m: m.get("vendor") == "Cisco" and m.get("interface_count", 0) >= 32 and m.get("l3_interface_count", 0) == 0,
    ],
    "leaf_switch": [
        # Strong: Arista + server-facing (leaf in DC fabric)
        lambda m: m.get("vendor") in ["Arista"] and m.get("l3_interface_count", 0) >= 2,
        # Moderate: High port count + L3 but no BGP (likely leaf)
        lambda m: m.get("interface_count", 0) >= 48 and m.get("l3_interface_count", 0) >= 2 and not m.get("has_bgp", False),
    ],
    "l2_firewall": [
        # Strong: firewall type + no NAT = L2 firewall
        lambda m: m.get("device_type") == "firewall" and not m.get("nat_enabled", False),
        # Moderate: firewall with ACLs but no routing
        lambda m: m.get("acl_count", 0) > 0 and not m.get("has_bgp", False) and not m.get("has_ospf", False),
    ],
    "l3_firewall": [
        # Strong: firewall type + NAT = L3 firewall
        lambda m: m.get("device_type") == "firewall" and m.get("nat_enabled", False),
        # Moderate: NAT + VPN (UTM-style firewall)
        lambda m: m.get("nat_enabled", False) and m.get("vpn_enabled", False),
    ],
    "load_balancer": [
        # Strong: F5/A10/Citrix vendor (explicit load balancer vendor)
        lambda m: m.get("vendor") in ["F5", "A10", "Citrix", "Kemp", "Radware"],
        # Moderate: VIP indicators (if available in metadata)
        lambda m: m.get("vip_count", 0) > 0,
    ],
    "server": [
        # Strong: explicit server device_type
        lambda m: m.get("device_type") == "server",
        # Moderate: OS indicators
        lambda m: m.get("os_type") in ["Linux", "Windows", "VMware", "Hyper-V"],
    ],
    "wireless_controller": [
        # Strong: wireless vendor + AP management capability
        lambda m: m.get("vendor") in ["Cisco", "Aruba", "Ruckus", "AeroHive"] and m.get("l3_interface_count", 0) >= 2,
        # Moderate: wireless enabled + management interface
        lambda m: m.get("wireless_enabled", False) and m.get("l3_interface_count", 0) >= 2,
    ],
    "access_point": [
        # Strong: explicit access_point device_type
        lambda m: m.get("device_type") == "access_point",
        # Moderate: wireless + low port count (typical AP)
        lambda m: m.get("wireless_enabled", False) and m.get("interface_count", 0) <= 4,
    ],
    "gateway": [
        # Strong: default route + NAT (internet gateway)
        lambda m: m.get("has_default_route", False) and m.get("nat_enabled", False),
    ],
    "datacenter_switch": [
        # Strong: high port count + Cisco/Juniper/Arista + no routing (DC core)
        lambda m: m.get("interface_count", 0) >= 48 and m.get("vendor") in ["Cisco", "Juniper", "Arista"] and m.get("l3_interface_count", 0) == 0,
    ],
    "endpoint_protection": [
        # Strong: endpoint security vendors
        lambda m: m.get("vendor") in ["Palo Alto", "CrowdStrike", "SentinelOne", "Sophos", "TrendMicro"],
    ],
    "vpn_concentrator": [
        # Strong: VPN enabled + specific port signatures
        lambda m: m.get("vpn_enabled", False) and (m.get("port_500_open", False) or m.get("port_4500_open", False)),
    ],
    "waf": [
        # Strong: explicit WAF vendors
        lambda m: m.get("vendor") in ["F5", "Imperva", "FortiWeb", "A10", "Citrix", "AWS", "Cloudflare"],
    ],
    "domain_controller": [
        # Strong: Microsoft AD indicators
        lambda m: m.get("vendor") == "Microsoft" and m.get("port_389_open", False),
    ],
}

# Fields confirmed in agent metadata schema (from CLAUDE.md and schemas.py)
CONFIRMED_METADATA_FIELDS = [
    "device_type", "vendor", "interface_count", "l3_interface_count", "vlan_count",
    "has_bgp", "has_ospf", "has_eigrp", "has_static_routes", "acl_count",
    "nat_enabled", "vpn_enabled", "wireless_enabled", "has_poe",
    "port_22_open", "port_23_open", "port_161_open", "port_443_open", "port_80_open",
]


class RoleClassifier:
    """Hybrid rule-based + ML device role classifier"""
    
    def __init__(self):
        self._ml_model = None
        self._model_version = "1.0.0"
    
    def classify(self, metadata: Dict) -> Dict:
        """Classify device role from metadata"""
        if not metadata:
            return self._unknown_result()
        
        # Try rule-based classification first
        role, confidence = self._rule_based_classify(metadata)
        
        if role != "unknown":
            return {
                "inferred_role": role,
                "confidence": confidence,
                "classified_at": datetime.utcnow(),
                "method": "rule_based",
                "features": self._extract_features(metadata),
            }
        
        # Fall back to ML model if available
        if self._ml_model:
            role, confidence = self._ml_classify(metadata)
            return {
                "inferred_role": role,
                "confidence": confidence,
                "classified_at": datetime.utcnow(),
                "method": "ml_model",
                "features": self._extract_features(metadata),
            }
        
        return self._unknown_result()
    
    def _rule_based_classify(self, metadata: Dict) -> Tuple[str, float]:
        """Rule-based classification"""
        best_role = "unknown"
        best_confidence = 0.0
        
        for role, rules in ROLE_RULES.items():
            for rule in rules:
                try:
                    if rule(metadata):
                        confidence = self._calculate_rule_confidence(role, metadata)
                        if confidence > best_confidence:
                            best_role = role
                            best_confidence = confidence
                except Exception:
                    pass
        
        return best_role, best_confidence
    
    def _calculate_rule_confidence(self, role: str, metadata: Dict) -> float:
        """
        Calculate confidence based on rule quality:
        - Single rule match: 0.6 (moderate confidence)
        - Multiple rule matches: 0.8 (high confidence)
        - device_type match as prerequisite: +0.1 bonus
        """
        rules = ROLE_RULES.get(role, [])
        matches = sum(1 for r in rules if r(metadata))
        
        # Base confidence from rule count
        if matches == 0:
            return 0.0
        elif matches == 1:
            base = 0.6
        else:
            base = 0.8
        
        # device_type match bonus (if device_type explicitly indicates this role)
        device_type = metadata.get("device_type", "").lower()
        role_device_types = {
            "core_router": ["router"],
            "edge_router": ["router"],
            "distribution_switch": ["switch"],
            "access_switch": ["switch"],
            "spine_switch": ["switch"],
            "leaf_switch": ["switch"],
            "datacenter_switch": ["switch"],
            "l2_firewall": ["firewall", "utm"],
            "l3_firewall": ["firewall", "utm"],
            "waf": ["firewall", "waf"],
            "server": ["server", "host", "vm"],
            "domain_controller": ["server", "host", "vm"],
            "access_point": ["access_point", "ap", "wireless"],
            "wireless_controller": ["wireless", "controller"],
            "load_balancer": ["load_balancer", "lb", "adc"],
            "vpn_concentrator": ["vpn", "firewall", "router"],
            "gateway": ["router", "firewall"],
            "endpoint_protection": ["security", "appliance"],
        }
        
        if role in role_device_types and device_type in role_device_types[role]:
            base = min(base + 0.1, 0.9)
        
        return base
    
    def _ml_classify(self, metadata: Dict) -> Tuple[str, float]:
        """ML-based classification (placeholder for Phase 2)"""
        return "unknown", 0.0
    
    def _extract_features(self, metadata: Dict) -> Dict:
        """Extract classification features from metadata"""
        return {
            "device_type": metadata.get("device_type"),
            "vendor": metadata.get("vendor"),
            "interface_count": metadata.get("interface_count", 0),
            "l3_interface_count": metadata.get("l3_interface_count", 0),
            "vlan_count": metadata.get("vlan_count", 0),
            "has_bgp": metadata.get("has_bgp", False),
            "has_ospf": metadata.get("has_ospf", False),
            "acl_count": metadata.get("acl_count", 0),
            "nat_enabled": metadata.get("nat_enabled", False),
            "vpn_enabled": metadata.get("vpn_enabled", False),
        }
    
    def _unknown_result(self) -> Dict:
        """Return unknown classification result"""
        return {
            "inferred_role": "unknown",
            "confidence": 0.0,
            "classified_at": datetime.utcnow(),
            "method": "none",
            "features": {},
        }
