"""Session operations: asking questions and managing transcripts.

Binding: ADR-0003 (transcript purge), ADR-0006 (intranet-only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from library_assistant.dependencies import SessionDep, get_settings
from library_assistant.models import AskRequest
from library_assistant.config import Settings

# Banner text constant as required by the AI literacy unit
BANNER_TEXT = "This can be wrong, check the source."


router = APIRouter(prefix="/session")


@router.post("/{session_id}/ask")
async def ask(
    session_id: str,
    request: AskRequest,
    session: SessionDep,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Ask a question and get a streamed answer with citations."""
    # Validate that we have a valid session
    if not session:
        raise HTTPException(status_code=400, detail="invalid session")
    
    # For now, return a simple mock response to ensure the endpoint works
    # In a real implementation, this would:
    # 1. Query the catalog for top 4 records
    # 2. Send prompt to OpenAI-compatible endpoint
    # 3. Stream the answer back with citations
    
    # Mock response for syntax validation
    async def generate_response():
        yield "Mock answer to: " + request.question
    
    return StreamingResponse(generate_response(), media_type="text/plain")