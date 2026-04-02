def test_full_classification_flow(client):
    """Test full device classification flow"""
    from app.db.database import engine
    from sqlalchemy import text
    import json
    import asyncio
    from uuid import uuid4
    
    device_id = str(uuid4())
    org_id = "00000000-0000-0000-0000-000000000001"
    
    meta = {
        "interface_count": 48,
        "l3_interface_count": 4,
        "has_bgp": True,
        "has_ospf": True,
        "vlan_count": 10,
        "vendor": "Cisco",
        "device_type": "router"
    }
    
    async def _setup():
        async with engine.connect() as conn:
            await conn.execute(text(f"""
                INSERT INTO devices (id, organization_id, ip_address, hostname, vendor, device_type, metadata)
                VALUES ('{device_id}', '{org_id}', '10.0.0.1', 'core-rtr-01', 'Cisco', 'router', '{json.dumps(meta)}')
            """))
            await conn.commit()
            
    asyncio.run(_setup())
    
    # 2. Trigger classification
    response = client.post(f"/api/v1/devices/{device_id}/classify")
    assert response.status_code == 200
    
    data = response.json()
    assert data["inferred_role"] in ["core_router", "distribution_switch", "unknown"]
    assert data["confidence"] >= 0.0
    
    # 3. Get classification
    response = client.get(f"/api/v1/devices/{device_id}/classification")
    assert response.status_code == 200
    
    data = response.json()
    assert "inferred_role" in data
    assert "confidence" in data
    
    # 4. Verify DB updated
    async def _verify():
        async with engine.connect() as conn:
            result = await conn.execute(text(f"SELECT inferred_role, role_confidence, role_classified_at FROM devices WHERE id = '{device_id}'"))
            row = result.fetchone()
            assert row[0] is not None
            assert row[1] is not None
            assert row[2] is not None

    asyncio.run(_verify())
