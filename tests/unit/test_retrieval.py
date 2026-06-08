"""
Unit tests for retrieval logic — RRF merge and permission filter.
No network calls — all logic is pure.
"""

from nexus_core.schemas.domain import Chunk, RankedChunk, RetrievedChunk
from nexus_retriever.hybrid import HybridRetriever
from nexus_retriever.reranker import PermissionFilter


def make_chunk(chunk_id: str, acl: list[str] | None = None) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        tenant_id="org_test",
        connector_id="google_drive",
        connection_id="conn_1",
        resource_id=f"res_{chunk_id}",
        resource_type="file",
        chunk_index=0,
        content=f"Content of chunk {chunk_id}",
        acl=acl or [],
    )


def make_retrieved(chunk_id: str, score: float, source: str = "dense") -> RetrievedChunk:
    return RetrievedChunk(
        chunk=make_chunk(chunk_id),
        score=score,
        source=source,
    )


class TestRRFMerge:
    def _rrf(self, lists, top_k=10):
        # Access private method via the class
        return HybridRetriever._rrf_merge(None, lists, top_k)  # type: ignore

    def test_single_list_preserves_order(self):
        results = [make_retrieved("a", 0.9), make_retrieved("b", 0.8), make_retrieved("c", 0.5)]
        merged = self._rrf([results])
        assert [r.chunk.chunk_id for r in merged] == ["a", "b", "c"]

    def test_chunk_appearing_in_both_lists_scores_higher(self):
        dense = [make_retrieved("shared", 0.9), make_retrieved("dense_only", 0.8)]
        sparse = [make_retrieved("shared", 0.7), make_retrieved("sparse_only", 0.6)]
        merged = self._rrf([dense, sparse])
        # "shared" should be first since it appears in both lists
        assert merged[0].chunk.chunk_id == "shared"

    def test_deduplication(self):
        # Same chunk in both lists — should appear once
        dense = [make_retrieved("a", 0.9), make_retrieved("b", 0.8)]
        sparse = [make_retrieved("a", 0.7), make_retrieved("c", 0.5)]
        merged = self._rrf([dense, sparse])
        ids = [r.chunk.chunk_id for r in merged]
        assert len(ids) == len(set(ids))

    def test_top_k_respected(self):
        results = [make_retrieved(str(i), 1.0 / (i + 1)) for i in range(20)]
        merged = self._rrf([results], top_k=5)
        assert len(merged) == 5

    def test_empty_input_returns_empty(self):
        assert self._rrf([]) == []
        assert self._rrf([[]]) == []


class TestPermissionFilter:
    def setup_method(self):
        self.filter = PermissionFilter()

    def _make_ranked(self, chunk_id: str, acl: list[str]) -> RankedChunk:
        return RankedChunk(
            chunk=make_chunk(chunk_id, acl=acl),
            rrf_score=1.0,
        )

    def test_no_user_email_returns_all(self):
        chunks = [
            self._make_ranked("a", ["alice@co.com"]),
            self._make_ranked("b", ["bob@co.com"]),
        ]
        result = self.filter.filter(chunks, user_email=None)
        assert len(result) == 2

    def test_user_can_see_own_chunks(self):
        chunks = [
            self._make_ranked("a", ["alice@co.com"]),
            self._make_ranked("b", ["bob@co.com"]),
        ]
        result = self.filter.filter(chunks, user_email="alice@co.com")
        assert len(result) == 1
        assert result[0].chunk.chunk_id == "a"

    def test_public_chunks_visible_to_all(self):
        chunks = [self._make_ranked("pub", ["public"])]
        result = self.filter.filter(chunks, user_email="anyone@example.com")
        assert len(result) == 1

    def test_empty_acl_defaults_to_visible(self):
        chunks = [self._make_ranked("no_acl", [])]
        result = self.filter.filter(chunks, user_email="user@co.com")
        assert len(result) == 1

    def test_case_insensitive_email_match(self):
        chunks = [self._make_ranked("a", ["Alice@Company.COM"])]
        result = self.filter.filter(chunks, user_email="alice@company.com")
        assert len(result) == 1

    def test_domain_wildcard_match(self):
        chunks = [self._make_ranked("a", ["@company.com"])]
        result = self.filter.filter(chunks, user_email="anyone@company.com")
        assert len(result) == 1

    def test_wrong_domain_denied(self):
        chunks = [self._make_ranked("a", ["@company.com"])]
        result = self.filter.filter(chunks, user_email="user@other.com")
        assert len(result) == 0
