"""知识库管理 — YAML 加载、关键词/模糊搜索、条目 CRUD"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from thefuzz import fuzz


@dataclass
class QAItem:
    """知识库问答条目"""

    id: int
    question: str
    keywords: list[str] = field(default_factory=list)
    answer: str = ""


class KnowledgeBase:
    """知识库，支持关键词精确匹配与 thefuzz 模糊匹配"""

    def __init__(self, path: str):
        self.path = path
        self.items: list[QAItem] = []
        self._load()

    # ------------------------------------------------------------------
    # 加载 / 重载
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """从 YAML 文件加载全部条目"""
        p = Path(self.path)
        if not p.exists():
            self.items = []
            return
        try:
            with open(p, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError:
            self.items = []
            return
        self.items = []
        if raw and "qa_pairs" in raw:
            for item in raw["qa_pairs"]:
                self.items.append(
                    QAItem(
                        id=item["id"],
                        question=item["question"],
                        keywords=item.get("keywords", []),
                        answer=item["answer"],
                    )
                )

    def reload(self) -> None:
        """从磁盘重新加载知识库（热更新）"""
        self._load()

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def search(
        self, question: str, threshold: int = 75
    ) -> Optional[tuple[str, str]]:
        """两阶段匹配：关键词精确子串 → thefuzz 模糊匹配

        Args:
            question: 用户输入的问题
            threshold: 模糊匹配最低分数（0-100）

        Returns:
            (answer, "kb") 当命中知识库，否则 None
        """
        if not question:
            return None

        # ---- Phase 1: 关键词精确子串匹配 --------------------------------
        for item in self.items:
            for keyword in item.keywords:
                if keyword in question:
                    return (item.answer, "kb")

        # ---- Phase 2: thefuzz partial_ratio 模糊匹配 --------------------
        best_score = 0
        best_item: Optional[QAItem] = None
        for item in self.items:
            score = fuzz.partial_ratio(question, item.question)
            if score > best_score:
                best_score = score
                best_item = item

        if best_score >= threshold and best_item is not None:
            return (best_item.answer, "kb")

        return None

    # ------------------------------------------------------------------
    # 条目管理（CRUD）
    # ------------------------------------------------------------------

    def add(
        self,
        question: str,
        answer: str,
        keywords: Optional[list[str]] = None,
    ) -> QAItem:
        """添加条目并持久化到 YAML 文件"""
        new_id = 1
        if self.items:
            new_id = max(item.id for item in self.items) + 1

        item = QAItem(
            id=new_id,
            question=question,
            keywords=keywords or [],
            answer=answer,
        )
        self.items.append(item)
        self._save()
        return item

    def delete(self, item_id: int) -> bool:
        """按 ID 删除条目，成功返回 True"""
        for i, item in enumerate(self.items):
            if item.id == item_id:
                self.items.pop(i)
                self._save()
                return True
        return False

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """将内存中的条目序列化写入 YAML 文件"""
        data = {
            "qa_pairs": [
                {
                    "id": item.id,
                    "question": item.question,
                    "keywords": item.keywords,
                    "answer": item.answer,
                }
                for item in self.items
            ]
        }
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
