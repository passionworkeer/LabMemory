"""Qwen 嵌入服务（DashScope OpenAI 兼容接口）。

无 API key 时降级为确定性 hash 伪向量：同文本同向量、相似文本弱语义相似。
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Literal

import httpx

from app.config import settings


EmbeddingMode = Literal["qwen-text-embedding-v3", "hash-fallback"]


class EmbeddingService:
    def __init__(self) -> None:
        self._model = settings.QWEN_EMBEDDING_MODEL
        self._dim = settings.QWEN_EMBEDDING_DIM
        self._api_key = settings.QWEN_API_KEY.strip()
        self._base_url = settings.QWEN_BASE_URL.rstrip("/")
        self._client = httpx.Client(timeout=30.0) if self._api_key else None

    @property
    def mode(self) -> EmbeddingMode:
        return "qwen-text-embedding-v3" if self._api_key else "hash-fallback"

    @property
    def dim(self) -> int:
        return self._dim

    def embed_texts(self, texts: list[str]) -> tuple[list[list[float]], EmbeddingMode]:
        if not texts:
            return [], self.mode
        if self._api_key and self._client:
            try:
                return self._embed_via_api(texts), "qwen-text-embedding-v3"
            except Exception:
                # API 调用失败时降级，保证 demo 可运行
                pass
        return [self._hash_embed(t) for t in texts], "hash-fallback"

    def embed_query(self, text: str) -> tuple[list[float], EmbeddingMode]:
        embs, mode = self.embed_texts([text])
        return embs[0] if embs else [0.0] * self._dim, mode

    def _embed_via_api(self, texts: list[str]) -> list[list[float]]:
        # DashScope OpenAI 兼容接口单次最多 25 条；分批处理
        out: list[list[float]] = []
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        for i in range(0, len(texts), 25):
            batch = texts[i : i + 25]
            payload = {
                "model": self._model,
                "input": batch,
                "encoding_format": "float",
            }
            resp = self._client.post(
                f"{self._base_url}/embeddings",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("data", []):
                out.append([float(x) for x in item["embedding"]])
        return out

    def _hash_embed(self, text: str) -> list[float]:
        """确定性 hash 伪向量：基于字符 n-gram 的哈希映射，L2 归一化。

        相同文本产生完全相同向量；相似文本因 n-gram 重叠产生弱相似度。
        仅用于 demo，不能替代真实语义嵌入。
        """
        vec = [0.0] * self._dim
        # 字符 3-gram
        s = text.lower()
        for n in (2, 3, 4):
            for i in range(max(0, len(s) - n + 1)):
                gram = s[i : i + n]
                h = int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16)
                idx = h % self._dim
                sign = 1.0 if (h >> 31) & 1 else -1.0
                vec[idx] += sign
        # L2 归一化
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
