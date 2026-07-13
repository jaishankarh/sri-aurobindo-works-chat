"""Document management API routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
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
