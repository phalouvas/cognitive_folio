from cognitive_folio.cognitive_folio.services.memory.embedding_provider import EmbeddingProvider


class SemanticSearch:
    """Compute semantic similarity scores between query and search results."""

    def __init__(self, embedding_provider=None):
        self.embedding_provider = embedding_provider or EmbeddingProvider()

    def score(self, query, result, dims=96, weight=0.6):
        text = self._result_text(result)
        if not query or not text:
            return 0.0

        query_vec = self.embedding_provider.embed_text(query, dims=dims)
        text_vec = self.embedding_provider.embed_text(text, dims=dims)
        similarity = self.embedding_provider.cosine_similarity(query_vec, text_vec)

        return max(0.0, float(similarity)) * max(0.0, float(weight or 0.0))

    def _result_text(self, result):
        result = result or {}
        return " ".join(
            [
                str(result.get("title") or "").strip(),
                str(result.get("snippet") or "").strip(),
            ]
        ).strip()
