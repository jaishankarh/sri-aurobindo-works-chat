#!/usr/bin/env python3
"""
Corpus PDF downloader for Sri Aurobindo Ashram publications.

Scrapes the official ashram websites to discover and download all available PDFs:
  1. Sri Aurobindo's writings: https://www.sriaurobindoashram.org/sriaurobindo/writings.php
  2. The Mother's works: https://www.sriaurobindoashram.org/mother/oeuvres.php

Downloaded PDFs are saved to the ./data/pdfs/ directory with structured filenames.
A manifest JSON file records all downloaded titles, authors, and paths.
"""

import asyncio
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
import aiofiles
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Target corpus URLs
CORPUS_SOURCES = [
    {
        "url": "https://www.sriaurobindoashram.org/sriaurobindo/writings.php",
        "author": "Sri Aurobindo",
        "base_url": "https://www.sriaurobindoashram.org",
    },
    {
        "url": "https://www.sriaurobindoashram.org/mother/oeuvres.php",
        "author": "The Mother",
        "base_url": "https://www.sriaurobindoashram.org",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AurobindoRAG/1.0; +https://github.com/aurobindo-rag)"
    )
}

MAX_CONCURRENT_DOWNLOADS = 3
DOWNLOAD_TIMEOUT = 300  # seconds per file


def _sanitize_filename(name: str) -> str:
    """Convert a title string to a safe filename."""
    name = re.sub(r"[^\w\s\-]", "", name).strip()
    name = re.sub(r"\s+", "_", name)
    return name[:100]  # truncate for filesystem safety


def _compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content of a page."""
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.text()


def _extract_pdf_links(html: str, base_url: str) -> list[dict]:
    """
    Extract all PDF links from an HTML page.

    Returns list of {title, url, filename} dicts.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not href.lower().endswith(".pdf"):
            continue

        absolute_url = urljoin(base_url, href)
        title = anchor.get_text(strip=True) or Path(urlparse(href).path).stem
        title = re.sub(r"\s+", " ", title).strip()

        links.append(
            {
                "title": title,
                "url": absolute_url,
                "filename": _sanitize_filename(title) + ".pdf",
            }
        )

    return links


async def _download_pdf(
    session: aiohttp.ClientSession,
    url: str,
    dest_path: Path,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Download a single PDF file with rate limiting."""
    async with semaphore:
        if dest_path.exists():
            logger.info(f"  Skip (exists): {dest_path.name}")
            return True

        logger.info(f"  Downloading: {dest_path.name}")
        try:
            async with session.get(
                url,
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT),
            ) as resp:
                resp.raise_for_status()
                content = await resp.read()

            async with aiofiles.open(dest_path, "wb") as f:
                await f.write(content)

            logger.info(f"  Saved: {dest_path.name} ({len(content) // 1024} KB)")
            return True

        except aiohttp.ClientError as e:
            logger.warning(f"  Failed to download {url}: {e}")
            return False
        except Exception as e:
            logger.error(f"  Unexpected error for {url}: {e}")
            return False


async def download_corpus(output_dir: str | Path = "./data/pdfs") -> list[dict]:
    """
    Main download function: scrape all corpus pages and download all PDFs.

    Returns a list of manifest entries for each downloaded file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    async with aiohttp.ClientSession() as session:
        for source in CORPUS_SOURCES:
            author = source["author"]
            author_dir = output_dir / _sanitize_filename(author)
            author_dir.mkdir(exist_ok=True)

            logger.info(f"\n{'='*60}")
            logger.info(f"Scraping: {source['url']}")
            logger.info(f"Author: {author}")
            logger.info(f"{'='*60}")

            try:
                html = await _fetch_page(session, source["url"])
            except Exception as e:
                logger.error(f"Failed to fetch {source['url']}: {e}")
                continue

            links = _extract_pdf_links(html, source["base_url"])

            if not links:
                logger.warning(f"No PDF links found on {source['url']}")
                logger.info("Note: The ashram website may require JavaScript or authentication.")
                logger.info("Please download PDFs manually and place them in: " + str(author_dir))
                continue

            logger.info(f"Found {len(links)} PDF links")

            # Download all PDFs concurrently (with semaphore rate limiting)
            tasks = []
            for link in links:
                dest = author_dir / link["filename"]
                task = asyncio.create_task(
                    _download_pdf(session, link["url"], dest, semaphore)
                )
                tasks.append((link, dest, task))

            for link, dest, task in tasks:
                success = await task
                if success or dest.exists():
                    manifest.append(
                        {
                            "title": link["title"],
                            "author": author,
                            "url": link["url"],
                            "file_path": str(dest),
                            "language": "fr" if author == "The Mother" else "en",
                            "downloaded": success,
                        }
                    )

    # Save manifest
    manifest_path = output_dir / "manifest.json"
    async with aiofiles.open(manifest_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(manifest, indent=2, ensure_ascii=False))

    logger.info(f"\nManifest saved to: {manifest_path}")
    logger.info(f"Total PDFs in manifest: {len(manifest)}")

    return manifest


async def ingest_from_manifest(manifest_path: str | Path) -> None:
    """
    Read the download manifest and queue all PDFs for RAG ingestion.

    Calls the backend ingestion API for each PDF in the manifest.
    """
    import httpx

    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        logger.error(f"Manifest not found: {manifest_path}")
        return

    with open(manifest_path) as f:
        manifest = json.load(f)

    api_base = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient(timeout=30) as client:
        for entry in manifest:
            if not Path(entry["file_path"]).exists():
                logger.warning(f"PDF not found, skipping: {entry['file_path']}")
                continue

            logger.info(f"Queuing ingestion: {entry['title']}")
            try:
                resp = await client.post(
                    f"{api_base}/documents/ingest",
                    json={
                        "file_path": entry["file_path"],
                        "title": entry["title"],
                        "author": entry["author"],
                    },
                )
                resp.raise_for_status()
                logger.info(f"  → Queued: {resp.json()}")
            except httpx.HTTPError as e:
                logger.error(f"  → Failed to queue: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Sri Aurobindo Ashram corpus PDFs")
    parser.add_argument(
        "--output-dir",
        default="./data/pdfs",
        help="Directory to save PDFs (default: ./data/pdfs)",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Also queue downloaded PDFs for RAG ingestion",
    )
    args = parser.parse_args()

    manifest = asyncio.run(download_corpus(args.output_dir))

    if args.ingest:
        manifest_path = Path(args.output_dir) / "manifest.json"
        asyncio.run(ingest_from_manifest(manifest_path))
