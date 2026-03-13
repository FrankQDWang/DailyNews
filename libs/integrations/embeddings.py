from __future__ import annotations

import hashlib


class EmbeddingAdapter:
    """Deterministic placeholder embedding adapter for MVP scaffolding.

    Replace with production embedding model when retrieval quality tuning starts.
    """

    dimension = 1536

    async def embed_text(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [digest[i % len(digest)] / 255.0 for i in range(self.dimension)]
        return values
