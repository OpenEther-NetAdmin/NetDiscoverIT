import pytest

def test_role_classifier_classify_core_router():
    from app.services.role_classifier import RoleClassifier
    
    classifier = RoleClassifier()
    metadata = {
        "device_type": "router",
        "interface_count": 48,
        "l3_interface_count": 4,
        "vlan_count": 10,
        "has_bgp": True,
        "has_ospf": True,
        "vendor": "Cisco"
    }
    
    result = classifier.classify(metadata)
    
    assert result["inferred_role"] == "core_router"
    assert result["confidence"] >= 0.8
