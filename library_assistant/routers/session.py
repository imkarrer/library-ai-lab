"""Session operations: asking questions and managing transcripts.

Binding: ADR-0003 (transcript purge), ADR-0006 (intranet-only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from library_assistant.catalog import Catalog
from library_assistant.config import Settings
from library_assistant.dependencies import SessionDep, get_catalog, get_settings
from library_assistant.models import AskRequest, Citation

# Banner text constant as required by the AI literacy unit
BANNER_TEXT = "This can be wrong, check the source."


router = APIRouter(prefix="/session")


@router.post("/{session_id}/ask")
async def ask(
    session_id: str,
    request: AskRequest,
    session: SessionDep,
    settings: Settings = Depends(get_settings),
    catalog: Catalog = Depends(get_catalog),
) -> StreamingResponse:
    """Ask a question and get a streamed answer with citations."""
    # Validate that we have a valid session
    if not session:
        raise HTTPException(status_code=400, detail="invalid session")

    # Query the catalog for top 4 records
    records = catalog.search(request.question, k=4)

    # Create citations from the records
    citations = [Citation(call_number=record.call_number) for record in records]

    # Mock response for syntax validation
    # In a real implementation, this would:
    # 1. Send prompt to OpenAI-compatible endpoint
    # 2. Stream the answer back with citations

    async def generate_response():
        yield "Mock answer to: " + request.question
        # Yield citations at the end (in a real implementation, these would be from the AI)
        for citation in citations:
            yield f"\nCitation: {citation.call_number}"

    return StreamingResponse(generate_response(), media_type="text/plain")
