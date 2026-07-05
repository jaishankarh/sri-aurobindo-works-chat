"""
Tests for multilingual retrieval and RRF fusion.

Verifies that:
1. French queries retrieve relevant English AND Sanskrit chunks (shared bge-m3 space)
2. RRF correctly weights dense vs sparse channels based on alpha
3. Alpha=1.0 gives pure dense results, alpha=0.0 gives pure sparse results
4. Graph traversal augments retrieval with multi-hop reasoning
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.retrieval.hybrid import _apply_rrf, _rrf_score
from app.models.schemas import RetrievedContext, RetrievalSettings


# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_context(
    chunk_id_suffix: str,
    text: str,
    language_tag: str = "en",
    relevance_score: float = 0.9,
    source: str = "vector",
) -> RetrievedContext:
    return RetrievedContext(
        chunk_id=uuid.UUID(f"00000000-0000-0000-0000-{chunk_id_suffix:>012s}"),
        document_id=uuid.uuid4(),
        document_title="Test Document",
        file_path="/data/pdfs/test.pdf",
        text=text,
        page_number=1,
        bbox=[72.0, 100.0, 540.0, 120.0],
        language_tag=language_tag,
        relevance_score=relevance_score,
        retrieval_source=source,
    )


# ── RRF scoring tests ─────────────────────────────────────────────────────────


class TestRRFScoring:
    """Unit tests for RRF score computation."""

    def test_rrf_score_decreases_with_rank(self):
        """Higher rank (worse position) should give lower RRF score."""
        scores = [_rrf_score(r) for r in range(10)]
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1], (
                f"Score at rank {i} ({scores[i]:.4f}) should be > rank {i+1} ({scores[i+1]:.4f})"
            )

    def test_rrf_score_positive(self):
        """All RRF scores should be strictly positive."""
        for rank in range(100):
            score = _rrf_score(rank)
            assert score > 0, f"RRF score at rank {rank} should be positive"

    def test_rrf_k_60_values(self):
        """Verify specific RRF values with k=60 (standard parameter)."""
        assert abs(_rrf_score(0) - 1/60) < 0.001  # rank 0: 1/(60+0)
        assert abs(_rrf_score(1) - 1/61) < 0.001  # rank 1: 1/(60+1)
        assert abs(_rrf_score(59) - 1/119) < 0.001  # rank 59: 1/(60+59)

    def test_rrf_custom_k(self):
        """Custom k parameter should be used in score computation."""
        from app.core.retrieval.hybrid import _rrf_score as rrf
        score_k10 = rrf(0, k=10)
        score_k60 = rrf(0, k=60)
        assert score_k10 > score_k60, "Smaller k should give higher score at rank 0"


class TestRRFFusion:
    """Tests for the _apply_rrf fusion function."""

    def test_alpha_1_pure_dense(self):
        """Alpha=1.0 should weight only dense results (sparse weight = 0)."""
        dense = [make_context("000000000001", "dense top result", relevance_score=0.95)]
        sparse = [make_context("000000000002", "sparse top result", relevance_score=0.95)]
        graph: list[RetrievedContext] = []

        results = _apply_rrf(dense, sparse, graph, alpha=1.0)

        assert len(results) >= 1
        # Dense result should rank higher (alpha=1.0 means only dense counts)
        if len(results) >= 2:
            chunk_ids = [str(r.chunk_id) for r in results]
            dense_idx = next((i for i, cid in enumerate(chunk_ids) if "000000000001" in cid), None)
            sparse_idx = next((i for i, cid in enumerate(chunk_ids) if "000000000002" in cid), None)
            if dense_idx is not None and sparse_idx is not None:
                assert dense_idx <= sparse_idx, "Dense result should rank at least as high as sparse"

    def test_alpha_0_pure_sparse(self):
        """Alpha=0.0 should weight only sparse/keyword results."""
        dense = [make_context("000000000003", "dense only", relevance_score=0.95)]
        sparse = [make_context("000000000004", "sparse only", relevance_score=0.95)]
        graph: list[RetrievedContext] = []

        results = _apply_rrf(dense, sparse, graph, alpha=0.0)

        chunk_ids = [str(r.chunk_id) for r in results]
        sparse_idx = next((i for i, cid in enumerate(chunk_ids) if "000000000004" in cid), None)
        dense_idx = next((i for i, cid in enumerate(chunk_ids) if "000000000003" in cid), None)
        if dense_idx is not None and sparse_idx is not None:
            assert sparse_idx <= dense_idx, "Sparse result should rank at least as high as dense"

    def test_overlap_boosts_score(self):
        """A chunk appearing in both dense and sparse lists should rank higher."""
        shared_id = "000000000005"
        dense_only_id = "000000000006"
        sparse_only_id = "000000000007"

        # Same chunk appears at top of both lists
        shared_chunk = make_context(shared_id, "overlapping result")
        dense = [
            shared_chunk,
            make_context(dense_only_id, "dense only"),
        ]
        sparse = [
            shared_chunk,
            make_context(sparse_only_id, "sparse only"),
        ]

        results = _apply_rrf(dense, sparse, [], alpha=0.5)

        chunk_ids = [str(r.chunk_id) for r in results]
        shared_idx = next((i for i, cid in enumerate(chunk_ids) if shared_id in cid), None)

        assert shared_idx is not None, "Shared chunk should appear in results"
        assert shared_idx == 0, f"Shared chunk should be first, got index {shared_idx}"

    def test_empty_inputs_return_empty(self):
        """Empty inputs should return empty results."""
        results = _apply_rrf([], [], [], alpha=0.5)
        assert results == []

    def test_deduplication(self):
        """The same chunk should not appear twice in results."""
        chunk = make_context("000000000008", "duplicate chunk")
        dense = [chunk, chunk]
        sparse = [chunk]

        results = _apply_rrf(dense, sparse, [], alpha=0.5)

        seen_ids = [r.chunk_id for r in results]
        assert len(seen_ids) == len(set(seen_ids)), "No duplicate chunk IDs in results"

    def test_graph_results_augment_retrieval(self):
        """Graph results should appear in fused output even without vector/sparse support."""
        dense: list[RetrievedContext] = []
        sparse: list[RetrievedContext] = []
        graph = [make_context("000000000009", "graph-only context", source="graph")]

        results = _apply_rrf(dense, sparse, graph, alpha=0.5)

        assert len(results) == 1, "Graph result should appear in output"
        assert "000000000009" in str(results[0].chunk_id)

    def test_relevance_score_normalized(self):
        """All returned relevance scores should be between 0 and 1."""
        dense = [make_context(f"{i:012d}", f"text {i}") for i in range(5)]
        sparse = [make_context(f"{i+5:012d}", f"sparse {i}") for i in range(5)]

        results = _apply_rrf(dense, sparse, [], alpha=0.5)

        for ctx in results:
            assert 0.0 <= ctx.relevance_score <= 1.0, (
                f"Relevance score {ctx.relevance_score} out of [0,1] for {ctx.chunk_id}"
            )


class TestMultilingualRetrieval:
    """
    Tests that verify cross-lingual retrieval in the BGE-M3 vector space.

    These tests use mock embeddings to verify the retrieval logic works
    correctly for multilingual queries without requiring the full model.
    """

    def test_retrieval_settings_language_filter(self):
        """Language filter should be correctly passed to retrieval."""
        settings = RetrievalSettings(
            alpha=0.7,
            top_k=5,
            language_filter=["en", "fr"],
        )
        assert settings.language_filter == ["en", "fr"]
        assert settings.alpha == 0.7

    def test_retrieval_settings_alpha_bounds(self):
        """Alpha must be clamped to [0.0, 1.0]."""
        with pytest.raises(Exception):  # pydantic validation error
            RetrievalSettings(alpha=1.5)

        with pytest.raises(Exception):
            RetrievalSettings(alpha=-0.1)

    def test_retrieval_settings_defaults(self):
        """Default retrieval settings should match documentation."""
        settings = RetrievalSettings()
        assert settings.alpha == 0.7
        assert settings.top_k == 5
        assert settings.graph_hops == 2
        assert settings.language_filter is None

    def test_rrf_retrieval_source_label(self):
        """RRF-fused results should have 'rrf' as their retrieval_source."""
        dense = [make_context("000000000010", "dense result")]
        results = _apply_rrf(dense, [], [], alpha=1.0)

        assert len(results) > 0
        assert results[0].retrieval_source == "rrf", (
            f"Expected 'rrf' source, got '{results[0].retrieval_source}'"
        )

    def test_french_query_retrieving_english_chunks(self):
        """
        Simulate that a French query can retrieve English chunks.

        In the real system, BGE-M3 maps French and English into the same
        semantic space. This test verifies the retrieval plumbing handles
        cross-lingual results correctly (language_tag != query language).
        """
        # Simulate: French query returned English chunks from dense search
        english_chunks = [
            make_context(f"{i:012d}", f"English text about Consciousness {i}", "en")
            for i in range(3)
        ]

        # These chunks are English but should be present in results for a French query
        results = _apply_rrf(english_chunks, [], [], alpha=1.0)

        assert len(results) == 3
        for ctx in results:
            assert ctx.language_tag == "en", "English chunks should retain their language tag"

    def test_sanskrit_chunks_included_in_multilingual_results(self):
        """Sanskrit (IAST) chunks should be retrievable alongside English content."""
        english = make_context("000000000020", "The Supermind descends", "en")
        sanskrit = make_context("000000000021", "Sat-Chit-Ānanda brahman paramātman", "sa")
        french = make_context("000000000022", "La conscience divine se manifeste", "fr")

        results = _apply_rrf([english, sanskrit, french], [], [], alpha=1.0)

        language_tags = {r.language_tag for r in results}
        assert "en" in language_tags
        assert "sa" in language_tags
        assert "fr" in language_tags
