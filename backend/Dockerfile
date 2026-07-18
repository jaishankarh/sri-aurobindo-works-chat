FROM python:3.11-slim

WORKDIR /app

# System dependencies for PyMuPDF and other native libraries.
# Cache mounts persist apt's package lists/archives across builds (unlike a
# regular layer, which gets invalidated — and re-downloaded — every time an
# earlier layer, e.g. requirements.txt, changes). Cache mount contents are
# never baked into the image, so this doesn't bloat the final image size.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl

# Install Python dependencies. Same cache-mount trick for pip's download/wheel
# cache — this is what actually matters here: torch + its bundled CUDA
# wheels alone are several GB, and requirements.txt changes on nearly every
# rebuild during iteration, which would otherwise invalidate the layer and
# force a full re-download every time.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data/pdfs /app/data/processed

# Download NLTK data for language detection
RUN python -c "import nltk; nltk.download('punkt', quiet=True)" 2>/dev/null || true

EXPOSE 8000

# Use uvicorn with multiple workers for production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
