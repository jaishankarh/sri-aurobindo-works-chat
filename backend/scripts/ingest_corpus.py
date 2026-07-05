#!/usr/bin/env python3
"""
Batch ingestion script for the corpus PDFs.

Reads all PDF files from a directory and ingests them through the full pipeline:
parse → embed → graph → store.

Usage:
    python scripts/ingest_corpus.py --pdf-dir ./data/pdfs
    python scripts/ingest_corpus.py --pdf-dir ./data/pdfs --batch-size 5
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def ingest_pdf(file_path: Path, author: str | None = None) -> dict:
    """Ingest a single PDF through the full pipeline."""
    # Add backend directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app.config import settings
    from app.database import get_async_session, init_db
    from app.services.ingestion import ingest_document

    async with get_async_session() as session:
        try:
            # Detect author from path structure
            if author is None and file_path.parent.name == "Sri_Aurobindo":
                author = "Sri Aurobindo"
            elif author is None and file_path.parent.name == "The_Mother":
                author = "The Mother"

            def progress_cb(status):
                logger.info(f"  [{status.status}] {status.progress:.0%} {status.message}")

            doc = await ingest_document(
                session=session,
                file_path=file_path,
                author=author,
                progress_callback=progress_cb,
            )
            await session.commit()
            logger.info(f"✓ Ingested: {doc.title} ({doc.id})")
            return {"status": "success", "document_id": str(doc.id), "title": doc.title}

        except Exception as e:
            logger.error(f"✗ Failed: {file_path.name}: {e}")
            await session.rollback()
            return {"status": "error", "file": str(file_path), "error": str(e)}


async def ingest_directory(pdf_dir: Path, batch_size: int = 3) -> list[dict]:
    """
    Ingest all PDFs in a directory, processing in batches.

    Args:
        pdf_dir: Root directory containing PDFs (may have subdirectories per author)
        batch_size: Number of PDFs to process concurrently

    Returns:
        List of ingestion result dicts.
    """
    pdf_files = sorted(pdf_dir.rglob("*.pdf"))

    if not pdf_files:
        logger.warning(f"No PDF files found in {pdf_dir}")
        return []

    logger.info(f"Found {len(pdf_files)} PDFs in {pdf_dir}")

    # Initialize database
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.database import init_db
    await init_db()

    results = []
    for i in range(0, len(pdf_files), batch_size):
        batch = pdf_files[i : i + batch_size]
        logger.info(f"\nProcessing batch {i // batch_size + 1}: {[p.name for p in batch]}")

        tasks = [ingest_pdf(p) for p in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in batch_results:
            if isinstance(result, Exception):
                results.append({"status": "error", "error": str(result)})
            else:
                results.append(result)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Batch ingest PDFs into the RAG system")
    parser.add_argument("--pdf-dir", default="./data/pdfs", help="Directory containing PDFs")
    parser.add_argument("--batch-size", type=int, default=3, help="Concurrent ingestion batch size")
    parser.add_argument("--output", help="Save results to JSON file")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        logger.error(f"Directory not found: {pdf_dir}")
        sys.exit(1)

    results = asyncio.run(ingest_directory(pdf_dir, batch_size=args.batch_size))

    success = sum(1 for r in results if r.get("status") == "success")
    failed = sum(1 for r in results if r.get("status") != "success")
    logger.info(f"\n{'='*50}")
    logger.info(f"Ingestion complete: {success} succeeded, {failed} failed")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to: {args.output}")
