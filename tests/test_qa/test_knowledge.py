"""KnowledgeBase 单元测试"""

import yaml
import pytest
from pathlib import Path

from src.plugins.qa.knowledge import KnowledgeBase, QAItem

# ------------------------------------------------------------------
# 夹具
# ------------------------------------------------------------------

SAMPLE_YAML = """
qa_pairs:
  - id: 1
    question: "群规是什么"
    keywords: ["群规", "规则", "规矩", "rules"]
    answer: "欢迎遵守群规，共同维护良好氛围！"
  - id: 2
    question: "今天天气怎么样"
    keywords: ["天气", "weather"]
    answer: "今天天气晴，气温20-25度。"
"""


@pytest.fixture
def kb_file(tmp_path: Path) -> str:
    path = tmp_path / "knowledge.yml"
    path.write_text(SAMPLE_YAML, encoding="utf-8")
    return str(path)


@pytest.fixture
def empty_kb_file(tmp_path: Path) -> str:
    path = tmp_path / "empty.yml"
    path.write_text("qa_pairs: []", encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------
# 测试：关键词精确子串匹配
# ------------------------------------------------------------------

class TestKeywordExactMatch:
    """关键词精确子串匹配（Phase 1）"""

    def test_keyword_in_question(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        # "群规" 是 question 的子串 → 命中
        result = kb.search("我想问一下群规是什么内容")
        assert result is not None
        assert result[0] == "欢迎遵守群规，共同维护良好氛围！"
        assert result[1] == "kb"

    def test_multiple_keywords_first_match(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        # "rules" 在 question 中 → 命中规则条目
        result = kb.search("what are the rules here")
        assert result is not None
        assert result[0] == "欢迎遵守群规，共同维护良好氛围！"

    def test_keyword_no_match(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        result = kb.search("完全没有关键词匹配的内容")
        assert result is None


# ------------------------------------------------------------------
# 测试：thefuzz 模糊匹配
# ------------------------------------------------------------------

class TestFuzzyMatch:
    """thefuzz partial_ratio 模糊匹配（Phase 2）"""

    def test_fuzzy_match_high_similarity(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        # "今天天气咋样" vs "今天天气怎么样" → partial_ratio 应 >= 75
        result = kb.search("今天天气咋样")
        assert result is not None
        assert result[0] == "今天天气晴，气温20-25度。"

    def test_fuzzy_match_exact_question(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        # 与 question 字段完全一致 → score = 100
        result = kb.search("今天天气怎么样")
        assert result is not None
        assert result[0] == "今天天气晴，气温20-25度。"

    def test_fuzzy_below_threshold(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        # 完全不相关的内容 → score < 75
        result = kb.search("明天会更好这首歌唱得真好")
        assert result is None


# ------------------------------------------------------------------
# 测试：无匹配
# ------------------------------------------------------------------

class TestNoMatch:
    """确定无匹配时应返回 None"""

    def test_random_string(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        result = kb.search("asdfghjkl")
        assert result is None

    def test_empty_question(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        result = kb.search("")
        assert result is None


# ------------------------------------------------------------------
# 测试：重载
# ------------------------------------------------------------------

class TestReload:
    """reload() 应重新读取 YAML 文件"""

    def test_reload_updates_items(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        assert len(kb.items) == 2

        # 向 YAML 追加新条目
        path = Path(kb_file)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["qa_pairs"].append(
            {
                "id": 3,
                "question": "机器人是什么",
                "keywords": ["机器人", "bot", "QQ机器人"],
                "answer": "本群机器人是基于 NoneBot2 框架开发的智能助手。",
            }
        )
        path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

        kb.reload()
        assert len(kb.items) == 3
        result = kb.search("什么是机器人")
        assert result is not None
        assert "NoneBot2" in result[0]


# ------------------------------------------------------------------
# 测试：空知识库
# ------------------------------------------------------------------

class TestEmptyKnowledgeBase:
    """空知识库不应影响正常运行"""

    def test_empty_kb_returns_none(self, empty_kb_file: str):
        kb = KnowledgeBase(empty_kb_file)
        assert kb.items == []
        result = kb.search("任何问题")
        assert result is None

    def test_nonexistent_file(self, tmp_path: Path):
        path = str(tmp_path / "nonexistent.yml")
        kb = KnowledgeBase(path)
        assert kb.items == []
        result = kb.search("任何问题")
        assert result is None


# ------------------------------------------------------------------
# 测试：条目管理（CRUD）
# ------------------------------------------------------------------

class TestCRUD:
    """add / delete 操作"""

    def test_add_item(self, tmp_path: Path):
        path = str(tmp_path / "dynamic.yml")
        Path(path).write_text("qa_pairs: []", encoding="utf-8")
        kb = KnowledgeBase(path)
        assert len(kb.items) == 0

        item = kb.add("测试问题", "测试答案", keywords=["测试"])
        assert item.id == 1
        assert item.question == "测试问题"
        assert len(kb.items) == 1

        # 应持久化到文件
        kb2 = KnowledgeBase(path)
        assert len(kb2.items) == 1
        assert kb2.items[0].question == "测试问题"

    def test_add_auto_id(self, tmp_path: Path):
        path = str(tmp_path / "auto_id.yml")
        data = {
            "qa_pairs": [
                {"id": 5, "question": "q1", "keywords": [], "answer": "a1"},
            ]
        }
        Path(path).write_text(
            yaml.dump(data, allow_unicode=True), encoding="utf-8"
        )
        kb = KnowledgeBase(path)
        item = kb.add("q2", "a2")
        assert item.id == 6

    def test_delete_existing(self, tmp_path: Path):
        path = str(tmp_path / "delete.yml")
        data = {
            "qa_pairs": [
                {"id": 1, "question": "q1", "keywords": [], "answer": "a1"},
                {"id": 2, "question": "q2", "keywords": [], "answer": "a2"},
            ]
        }
        Path(path).write_text(
            yaml.dump(data, allow_unicode=True), encoding="utf-8"
        )
        kb = KnowledgeBase(path)
        assert len(kb.items) == 2

        assert kb.delete(1) is True
        assert len(kb.items) == 1
        assert kb.items[0].id == 2

        # 应同步到文件
        kb2 = KnowledgeBase(path)
        assert len(kb2.items) == 1

    def test_delete_nonexistent(self, kb_file: str):
        kb = KnowledgeBase(kb_file)
        assert kb.delete(999) is False
        assert len(kb.items) == 2
