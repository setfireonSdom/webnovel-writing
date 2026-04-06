"""
RAG 适配器 (基于 BM25 关键词匹配，完全免费，无需额外 API)
"""

import json
import logging
import os
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional

import jieba
from rank_bm25 import BM25Okapi

from ..utils.file_ops import read_text_file, ensure_directory

logger = logging.getLogger(__name__)


class BM25RAG:
    """基于 BM25 的检索增强生成"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.index_dir = project_root / ".webnovel" / "rag_index"
        ensure_directory(self.index_dir)
        
        self.index_file = self.index_dir / "bm25_index.pkl"
        self.chunks_file = self.index_dir / "chunks.json"
        
        self.bm25: Optional[BM25Okapi] = None
        self.chunks: List[Dict[str, Any]] = []
        
        self._load_index()

    def _load_index(self):
        """加载索引"""
        if self.index_file.exists() and self.chunks_file.exists():
            try:
                with open(self.index_file, "rb") as f:
                    self.bm25 = pickle.load(f)
                with open(self.chunks_file, "r", encoding="utf-8") as f:
                    saved_chunks = json.load(f)
                # 恢复 tokens（从 content 重新分词）
                self.chunks = []
                for chunk in saved_chunks:
                    tokens = list(jieba.cut(chunk["content"]))
                    self.chunks.append({
                        "chapter": chunk["chapter"],
                        "content": chunk["content"],
                        "tokens": tokens,
                    })
                logger.info(f"RAG 索引加载成功，共 {len(self.chunks)} 个块")
            except Exception as e:
                logger.error(f"加载 RAG 索引失败: {e}")
                self.bm25 = None
                self.chunks = []

    def add_chapter(self, chapter_num: int, content: str):
        """索引新章节"""
        logger.info(f"正在索引第 {chapter_num} 章...")

        # 简单分块：按段落分
        paragraphs = [p.strip() for p in content.split("\n") if len(p.strip()) > 20]

        # 分词
        tokenized_docs = [list(jieba.cut(p)) for p in paragraphs]

        # 构建块信息
        new_chunks = []
        for i, doc in enumerate(tokenized_docs):
            new_chunks.append({
                "chapter": chapter_num,
                "content": paragraphs[i],
                "tokens": doc,
            })

        # 追加到现有块
        self.chunks.extend(new_chunks)

        # 重新构建 BM25 索引
        all_tokens = [c["tokens"] for c in self.chunks]
        self.bm25 = BM25Okapi(all_tokens)

        # 保存
        self._save_index()
        logger.info(f"第 {chapter_num} 章 RAG 索引建立完成，共 {len(self.chunks)} 个块")

    def _save_index(self):
        """保存索引"""
        try:
            with open(self.index_file, "wb") as f:
                pickle.dump(self.bm25, f)
            # 保存 chunks 时去掉 tokens 以减小体积（tokens 仅用于构建 BM25）
            chunks_to_save = [
                {"chapter": c["chapter"], "content": c["content"]}
                for c in self.chunks
            ]
            with open(self.chunks_file, "w", encoding="utf-8") as f:
                json.dump(chunks_to_save, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存 RAG 索引失败: {e}")

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """检索相关内容"""
        if not self.bm25:
            return []
        
        query_tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(query_tokens)
        
        # 获取 Top-K
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                chunk = self.chunks[idx]
                results.append({
                    "chapter": chunk["chapter"],
                    "content": chunk["content"],
                    "score": float(scores[idx]),
                })
        
        return results
