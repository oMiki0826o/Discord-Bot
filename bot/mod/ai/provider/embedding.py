"""
bot/mod/ai/provider/embedding.py

Modification():

- 建立 Gemini Embedding adapter 與固定維度驗證。

本檔案將 SDK response 轉成 Retrieval 使用的 float tuple。
"""

from __future__ import annotations

from typing import Any


class GeminiEmbeddingProvider:
    def __init__(self, client: Any, *, model: str, dimensions: int) -> None:
        if not model.strip() or dimensions < 1:
            raise ValueError("embedding model/dimensions are invalid")
        self.client = client
        self.model = model
        self.dimensions = dimensions

    async def __call__(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise ValueError("embedding text must not be blank")
        response = await self.client.aio.models.embed_content(
            model=self.model,
            contents=text,
            config={"output_dimensionality": self.dimensions},
        )
        embeddings = getattr(response, "embeddings", None) or ()
        if not embeddings:
            raise RuntimeError("embedding provider returned no vectors")
        values = tuple(float(value) for value in embeddings[0].values)
        if len(values) != self.dimensions:
            raise RuntimeError("embedding dimensions do not match configuration")
        return values
