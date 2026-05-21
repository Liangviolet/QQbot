"""Bilibili 解析器单元测试"""

from src.plugins.bilibili.parser import extract_bv_ids, format_duration


class TestExtractBvIds:
    """BV 号提取功能测试"""

    def test_single_bv(self):
        """单个 BV 号提取"""
        result = extract_bv_ids("看看这个视频 BV1xx411c7mD")
        assert result == ["BV1xx411c7mD"]

    def test_multiple_bv_two(self):
        """多个 BV 号提取（2 个）"""
        result = extract_bv_ids("BV1xx411c7mD 和 BV1xx411c7mE")
        assert result == ["BV1xx411c7mD", "BV1xx411c7mE"]

    def test_multiple_bv_five_limit_three(self):
        """超过 max_count 时只返回前 max_count 个"""
        text = "BV1xx411c7m1 BV1xx411c7m2 BV1xx411c7m3 BV1xx411c7m4 BV1xx411c7m5"
        result = extract_bv_ids(text, max_count=3)
        assert len(result) == 3
        assert result == ["BV1xx411c7m1", "BV1xx411c7m2", "BV1xx411c7m3"]

    def test_no_bv(self):
        """无 BV 号返回空列表"""
        result = extract_bv_ids("今天的天气真好")
        assert result == []

    def test_deduplication(self):
        """重复的 BV 号去重"""
        result = extract_bv_ids("BV1xx411c7mD 和 BV1xx411c7mD")
        assert result == ["BV1xx411c7mD"]

    def test_lowercase_bv_not_match(self):
        """小写 bv 前缀不应匹配"""
        result = extract_bv_ids("bv1xx411c7md")
        assert result == []

    def test_url_embedded_bv(self):
        """URL 中嵌入的 BV 号应被提取"""
        result = extract_bv_ids("https://www.bilibili.com/video/BV1xx411c7mD")
        assert result == ["BV1xx411c7mD"]

    def test_mixed_text_with_bv(self):
        """混合文本中的 BV 号"""
        result = extract_bv_ids("【震惊】BV1xx411c7mD 这个视频太厉害了！")
        assert result == ["BV1xx411c7mD"]

    def test_empty_string(self):
        """空字符串"""
        result = extract_bv_ids("")
        assert result == []


class TestFormatDuration:
    """时长格式化测试"""

    def test_zero_seconds(self):
        """0 秒"""
        assert format_duration(0) == "0:00"

    def test_under_minute(self):
        """不足 1 分钟"""
        assert format_duration(45) == "0:45"
        assert format_duration(59) == "0:59"

    def test_exact_minute(self):
        """整分钟"""
        assert format_duration(60) == "1:00"
        assert format_duration(120) == "2:00"

    def test_minutes_and_seconds(self):
        """分钟 + 秒"""
        assert format_duration(61) == "1:01"
        assert format_duration(3661) == "1:01:01"

    def test_hours(self):
        """超过 1 小时"""
        assert format_duration(3600) == "1:00:00"
        assert format_duration(7200) == "2:00:00"

    def test_hours_with_seconds(self):
        """小时 + 分钟 + 秒"""
        assert format_duration(3661) == "1:01:01"
        assert format_duration(7384) == "2:03:04"
