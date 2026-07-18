"""Document management API routes."""

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.graph import delete_document_graph
from app.database import get_db_session
from app.models.database import Document
from app.models.schemas import DocumentResponse, IngestionRequest, IngestionStatus

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    db: AsyncSession = Depends(get_db_session),
) -> list[DocumentResponse]:
    """List all ingested documents."""
    result = await db.execute(select(Document).order_by(Document.ingested_at.desc()))
    docs = result.scalars().all()
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    """Get a single document by ID."""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    """
    Stream the source PDF for a document.

    The frontend's PDF viewer fetches this rather than the raw filesystem
    path stored in Citation.file_path — that path is only meaningful inside
    the backend container, not to the browser.
    """
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    # content_disposition_type="inline" (not the default "attachment") so
    # that navigating to this URL directly displays the PDF in-browser
    # instead of forcing a download — react-pdf's own fetch doesn't care
    # either way, but a stray/direct visit to this URL should still behave
    # like viewing a PDF, not downloading one.
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


@router.post("/ingest", response_model=IngestionStatus)
async def ingest_document_endpoint(
    request: IngestionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
) -> IngestionStatus:
    """
    Queue a document for ingestion via Prefect.

    The ingestion runs as a background Prefect flow, enabling progress tracking
    and retry on failure.
    """
    from app.workers.prefect_flows import ingest_document_flow

    async def _run_flow():
        await ingest_document_flow(
            file_path=request.file_path,
            title=request.title,
            author=request.author,
            force_reingest=request.force_reingest,
        )

    background_tasks.add_task(_run_flow)

    return IngestionStatus(
        status="queued",
        progress=0.0,
        message=f"Queued {request.file_path} for ingestion",
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a document, its chunks (Postgres), and its graph entities (Neo4j)."""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await delete_document_graph(str(document_id))
    await db.delete(doc)
