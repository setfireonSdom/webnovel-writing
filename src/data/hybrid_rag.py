"""
向量 RAG 适配器
支持 Embedding + Rerank 混合检索
"""

import logging
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx

from ..utils.file_ops import read_text_file, ensure_directory

logger = logging.getLogger(__name__)


class EmbeddingAdapter:
    """Embedding 模型适配器"""

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get("base_url", "https://api-inference.modelscope.cn/v1")
        self.model = config.get("model", "Qwen/Qwen3-Embedding-8B")
        self.api_key = config.get("api_key", "")
        self.timeout = config.get("timeout", 30)

    async def encode(self, texts: List[str]) -> List[List[float]]:
        """编码文本为向量"""
        if not self.api_key:
            logger.warning("Embedding API Key 未配置，返回空列表")
            return [[] for _ in texts]

        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # 提取 embeddings
                embeddings = [item["embedding"] for item in data.get("data", [])]
                return embeddings
        except Exception as e:
            logger.error(f"Embedding 调用失败: {e}")
            return [[] for _ in texts]

    async def encode_single(self, text: str) -> List[float]:
        """编码单个文本"""
        result = await self.encode([text])
        return result[0] if result else []


class RerankAdapter:
    """Rerank 模型适配器"""

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get("base_url", "https://api.jina.ai/v1")
        self.model = config.get("model", "jina-reranker-v3")
        self.api_key = config.get("api_key", "")
        self.timeout = config.get("timeout", 30)

    async def rerank(self, query: str, documents: List[str], top_k: int = 5) -> List[Dict[str, Any]]:
        """重排序文档"""
        if not self.api_key:
            logger.warning("Rerank API Key 未配置，返回原始顺序")
            return [{"index": i, "score": 0.0, "document": doc} for i, doc in enumerate(documents)]

        url = f"{self.base_url}/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_k,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # 提取 rerank 结果
                results = []
                for item in data.get("results", []):
                    results.append({
                        "index": item.get("index", 0),
                        "score": item.get("relevance_score", 0.0),
                        "document": documents[item.get("index", 0)] if item.get("index", 0) < len(documents) else "",
                    })
                
                return results
        except Exception as e:
            logger.error(f"Rerank 调用失败: {e}")
            # 返回原始顺序
            return [{"index": i, "score": 0.0, "document": doc} for i, doc in enumerate(documents[:top_k])]


class HybridRAG:
    """混合 RAG 系统（BM25 + 向量检索）"""

    def __init__(self, project_root: Path, embedding_config: Dict = None, rerank_config: Dict = None):
        self.project_root = project_root
        self.vector_dir = project_root / ".webnovel" / "vector_index"
        ensure_directory(self.vector_dir)

        self.vector_file = self.vector_dir / "vectors.json"
        self.chunks: List[Dict[str, Any]] = []
        self.embeddings: List[List[float]] = []

        # 初始化适配器
        self.embedding_adapter = EmbeddingAdapter(embedding_config or {})
        self.rerank_adapter = RerankAdapter(rerank_config or {})

        self._load_index()

    def _load_index(self):
        """加载向量索引"""
        if self.vector_file.exists():
            try:
                data = json.loads(read_text_file(self.vector_file))
                self.chunks = data.get("chunks", [])
                self.embeddings = data.get("embeddings", [])
                logger.info(f"向量索引加载成功，共 {len(self.chunks)} 个块")
            except Exception as e:
                logger.error(f"加载向量索引失败: {e}")
                self.chunks = []
                self.embeddings = []

    def _save_index(self):
        """保存向量索引"""
        try:
            data = {
                "chunks": self.chunks,
                "embeddings": self.embeddings,
            }
            with open(self.vector_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存向量索引失败: {e}")

    async def add_chapter(self, chapter_num: int, content: str):
        """索引新章节"""
        logger.info(f"正在为第 {chapter_num} 章建立向量索引...")

        # 分块（按段落）
        paragraphs = [p.strip() for p in content.split("\n") if len(p.strip()) > 50]

        if not paragraphs:
            return

        # 编码为向量
        embeddings = await self.embedding_adapter.encode(paragraphs)

        # 存储
        for i, (para, emb) in enumerate(zip(paragraphs, embeddings)):
            if emb:  # 只保存成功编码的
                self.chunks.append({
                    "chapter": chapter_num,
                    "content": para,
                    "embedding_index": len(self.embeddings),
                })
                self.embeddings.append(emb)

        self._save_index()
        logger.info(f"第 {chapter_num} 章向量索引建立完成，共 {len(paragraphs)} 个块")

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2:
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(a * a for a in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    async def retrieve_vector(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """向量检索"""
        if not self.embeddings:
            return []

        # 编码查询
        query_emb = await self.embedding_adapter.encode_single(query)
        if not query_emb:
            return []

        # 计算相似度
        scores = []
        for i, chunk_emb in enumerate(self.embeddings):
            if chunk_emb:
                score = self._cosine_similarity(query_emb, chunk_emb)
                scores.append((i, score))

        # 排序并返回 Top-K
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scores[:top_k]:
            if idx < len(self.chunks):
                results.append({
                    "chapter": self.chunks[idx]["chapter"],
                    "content": self.chunks[idx]["content"],
                    "score": score,
                })

        return results

    async def retrieve_hybrid(
        self,
        query: str,
        bm25_results: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """混合检索（BM25 + 向量 + Rerank）"""
        # 1. 向量检索
        vector_results = await self.retrieve_vector(query, top_k=top_k)

        # 2. 合并结果
        all_docs = []
        seen = set()

        for res in bm25_results:
            key = (res["chapter"], res["content"])
            if key not in seen:
                all_docs.append(res["content"])
                seen.add(key)

        for res in vector_results:
            key = (res["chapter"], res["content"])
            if key not in seen:
                all_docs.append(res["content"])
                seen.add(key)

        if not all_docs:
            return bm25_results

        # 3. Rerank
        reranked = await self.rerank_adapter.rerank(query, all_docs, top_k=top_k)

        # 4. 构建最终结果
        final_results = []
        for item in reranked:
            # 找到原始的章节信息
            for res in (bm25_results + vector_results):
                if res["content"] == item["document"]:
                    final_results.append({
                        "chapter": res["chapter"],
                        "content": res["content"],
                        "score": item["score"],
                    })
                    break

        return final_results[:top_k]
