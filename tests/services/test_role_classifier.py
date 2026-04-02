import pytest
from uuid import uuid4

def test_device_model_has_role_columns():
    from app.models.models import Device
    
    device = Device(
        id=uuid4(),
        organization_id=uuid4(),
        ip_address="192.168.1.1",
        inferred_role=None,
        role_confidence=None
    )
    
    # Verify the column names match the actual model
    assert hasattr(device, 'inferred_role')
    assert hasattr(device, 'role_confidence')
    assert hasattr(device, 'role_classified_at')
    assert hasattr(device, 'role_classifier_version')
    
    # CRITICAL: Verify meta column exists (not device_metadata)
    assert hasattr(device, 'meta')
