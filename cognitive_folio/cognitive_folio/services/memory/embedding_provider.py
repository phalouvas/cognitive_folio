import hashlib
import math
import re


class EmbeddingProvider:
    """Deterministic local embedding provider used for vector-memory ranking."""

    def embed_text(self, text, dims=96):
        dims = max(16, int(dims or 96))
        cleaned = str(text or "").lower().strip()
        if not cleaned:
            return [0.0] * dims

        vector = [0.0] * dims
        features = self._features(cleaned)
        for feature in features:
            index = self._feature_index(feature, dims)
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            return vector

        return [value / norm for value in vector]

    def cosine_similarity(self, a, b):
        if not a or not b:
            return 0.0

        limit = min(len(a), len(b))
        if limit <= 0:
            return 0.0

        return float(sum(float(a[i]) * float(b[i]) for i in range(limit)))

    def _features(self, cleaned):
        words = [token for token in re.split(r"[^a-z0-9.]+", cleaned) if token]
        features = []

        for word in words:
            features.append(f"w:{word}")
            if len(word) >= 4:
                for i in range(0, len(word) - 2):
                    features.append(f"g:{word[i:i + 3]}")

        return features or ["empty"]

    def _feature_index(self, feature, dims):
        digest = hashlib.sha256(feature.encode("utf-8", errors="ignore")).hexdigest()
        return int(digest[:8], 16) % dims
