"""Tests that change_service generates timezone-aware datetimes."""
import pytest
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_generate_change_number_uses_timezone_aware_year():
    """generate_change_number must use timezone-aware datetime for year extraction."""
    from app.services.change_service import generate_change_number
    from datetime import datetime, timezone

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar.return_value = 0
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await generate_change_number(mock_db)
    expected_year = datetime.now(timezone.utc).year
    assert result.startswith(f"CHG-{expected_year}-"), (
        f"Expected CHG-{expected_year}-NNNN, got {result}"
    )
