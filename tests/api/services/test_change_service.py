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


@pytest.mark.asyncio
async def test_generate_change_number_no_duplicates_under_concurrency():
    """Concurrent calls must produce unique change numbers."""
    from app.services.change_service import generate_change_number
    from unittest.mock import AsyncMock, MagicMock, call
    from sqlalchemy.ext.asyncio import AsyncSession
    import asyncio

    call_count = 0

    async def mock_execute(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        return mock_result

    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(side_effect=mock_execute)

    results = await asyncio.gather(
        generate_change_number(mock_db),
        generate_change_number(mock_db),
    )
    assert mock_db.execute.call_count >= 2, "Expected at least 2 DB calls (lock + count)"
    all_calls = [str(c) for c in mock_db.execute.call_args_list]
    assert any("pg_advisory_xact_lock" in c for c in all_calls), (
        "generate_change_number must acquire a pg_advisory_xact_lock before counting"
    )
