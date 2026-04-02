"""
NLI route — POST /query
Natural language query interface over pgvector + Neo4j + Claude.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import dependencies, schemas
from app.api.dependencies import get_current_user, get_db
from app.api.rate_limit import limiter, LIMIT_NLI
from app.core.config import settings
from app.db.neo4j import get_neo4j_client

router = APIRouter()

# Module-level NLI service instance — loaded once on first request to avoid
# loading sentence-transformers at import time (adds ~3s to cold start for all tests)
_nli_service = None


def get_nli_service():
    global _nli_service
    if _nli_service is None:
        from app.services.nli.nli_service import NLIService
        _nli_service = NLIService(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
        )
    return _nli_service


@router.post("", response_model=schemas.NLIResponse)
@limiter.limit(LIMIT_NLI)
async def natural_language_query(
    request: Request,
    query: schemas.NLIQuery,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
):
    """
    Answer a natural-language question about your network.

    The pipeline embeds the question, searches pgvector for relevant devices,
    optionally traverses Neo4j for topology context, then synthesises an answer
    via Claude. Returns the answer, source devices, and a confidence score.
    """
    if not query.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty")

    nli = get_nli_service()

    if not nli.available:
        raise HTTPException(
            status_code=503,
            detail="NLI service not available: ANTHROPIC_API_KEY is not configured",
        )

    # Get Neo4j client (None if unavailable — pipeline degrades gracefully)
    try:
        neo4j_client = get_neo4j_client()
    except Exception:
        neo4j_client = None

    top_k = min(query.top_k, 20)

    try:
        result = await nli.query(
            db=db,
            neo4j_client=neo4j_client,
            question=query.question,
            org_id=str(current_user.organization_id),
            top_k=top_k,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Claude API request timed out")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"NLI pipeline error: {exc}")

    return result