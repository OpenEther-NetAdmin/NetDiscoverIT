# Python Style Guide

## Imports

Group imports with blank lines between groups:
1. Standard library
2. Third-party packages
3. Local app modules (`from app.xxx import ...`)

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.db.database import get_db
```

## Formatting

- Max line length: 120 (enforced via flake8)
- Use double quotes for strings
- Use Black for auto-formatting

## Type Hints

- Use type hints for function signatures
- Use Pydantic v2 models for schemas (`model_dump()` not `dict()`)
- Async SQLAlchemy: `AsyncSession`, `await` all DB operations

## Naming Conventions

- `snake_case` for variables, functions, methods
- `PascalCase` for classes
- `UPPER_CASE` for constants/settings
- Model classes match table name (e.g., `Device` → `devices`)

## Error Handling

- Use FastAPI `HTTPException` for API errors
- Log warnings for non-fatal failures during startup
- Fail loudly at startup if required secrets unset (no defaults for secrets)

## Compatibility

- Use `from __future__ import annotations` for Python 3.9+ compatibility
- Use `Union[X, Y]` instead of `X | Y` for broader compatibility
- Test with Python 3.9 minimum in CI
