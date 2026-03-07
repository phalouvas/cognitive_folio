import unittest

from cognitive_folio.cognitive_folio.services.memory.embedding_provider import EmbeddingProvider


class TestEmbeddingProvider(unittest.TestCase):
    def test_embed_text_is_deterministic(self):
        provider = EmbeddingProvider()
        first = provider.embed_text("TSLA volatility", dims=64)
        second = provider.embed_text("TSLA volatility", dims=64)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_cosine_similarity_prefers_related_text(self):
        provider = EmbeddingProvider()

        query = provider.embed_text("volatile TSLA risk", dims=64)
        related = provider.embed_text("TSLA volatility risk is elevated", dims=64)
        unrelated = provider.embed_text("consumer staples dividend schedule", dims=64)

        related_score = provider.cosine_similarity(query, related)
        unrelated_score = provider.cosine_similarity(query, unrelated)

        self.assertGreater(related_score, unrelated_score)
