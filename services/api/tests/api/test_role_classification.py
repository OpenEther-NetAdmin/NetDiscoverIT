import pytest
from uuid import uuid4
import asyncio

@pytest.fixture
def test_device(client):
    """Create a device in the database for testing"""
    from app.db.database import engine
    from sqlalchemy import text
    import json
    
    device_id = str(uuid4())
    org_id = "00000000-0000-0000-0000-000000000001" # FIXTED_ORG_ID from conftest
    
    meta = {
        "interface_count": 48,
        "l3_interface_count": 4,
        "vlan_count": 10,
        "has_bgp": True,
        "has_ospf": True,
        "vendor": "Cisco",
        "device_type": "router"
    }
    
    async def _setup():
        async with engine.connect() as conn:
            await conn.execute(text(f"""
                INSERT INTO devices (id, organization_id, ip_address, metadata) 
                VALUES ('{device_id}', '{org_id}', '192.168.1.1', '{json.dumps(meta)}')
            """))
            await conn.commit()
            
    asyncio.run(_setup())
    return device_id

def test_classify_device_endpoint(client, test_device):
    response = client.post(f"/api/v1/devices/{test_device}/classify")
    
    assert response.status_code == 200
    data = response.json()
    assert "inferred_role" in data
    assert "confidence" in data
    assert data["inferred_role"] == "core_router"

def test_batch_classify_devices(client):
    from app.db.database import engine
    from sqlalchemy import text
    import json
    
    org_id = "00000000-0000-0000-0000-000000000001"
    device_ids = [str(uuid4()) for _ in range(3)]
    
    meta = {
        "interface_count": 48,
        "l3_interface_count": 4,
        "has_bgp": True,
        "vendor": "Cisco",
        "device_type": "router"
    }
    
    async def _setup():
        async with engine.connect() as conn:
            for device_id in device_ids:
                await conn.execute(text(f"""
                    INSERT INTO devices (id, organization_id, ip_address, metadata) 
                    VALUES ('{device_id}', '{org_id}', '192.168.1.1', '{json.dumps(meta)}')
                """))
            await conn.commit()
            
    asyncio.run(_setup())
    
    response = client.post("/api/v1/devices/classify-batch", json={
        "device_ids": device_ids
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 3
