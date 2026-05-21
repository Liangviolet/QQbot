"""BV 号解析与 B站 API"""

import re
from dataclasses import dataclass
from typing import Optional

import httpx

# 使用 (?<!\w)/(?!\w) 替代 \b，兼容 CJK 字符（Python re 中 CJK 属于 \w）
BV_PATTERN = re.compile(r"(?<!\w)(BV[1-9A-HJ-NP-Za-km-z]{10})(?!\w)")


@dataclass
class VideoInfo:
    bvid: str
    title: str
    author: str
    views: int
    cover_url: str
    duration: int  # 秒


def extract_bv_ids(text: str, max_count: int = 3) -> list[str]:
    """从文本中提取 BV 号，最多 max_count 个，去重"""
    matches = BV_PATTERN.findall(text)
    seen = set()
    result = []
    for bv in matches:
        if bv not in seen:
            seen.add(bv)
            result.append(bv)
            if len(result) >= max_count:
                break
    return result


async def fetch_video_info(bvid: str, client: httpx.AsyncClient) -> Optional[VideoInfo]:
    """调用 B站 API 获取视频信息
    API: https://api.bilibili.com/x/web-interface/view?bvid={bvid}
    返回 None 表示视频无效或 API 错误
    """
    try:
        resp = await client.get(
            f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
            timeout=10.0,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            return None
        v = data["data"]
        return VideoInfo(
            bvid=bvid,
            title=v["title"],
            author=v["owner"]["name"],
            views=v["stat"]["view"],
            cover_url=v["pic"],
            duration=v["duration"],
        )
    except Exception:
        return None


def format_duration(seconds: int) -> str:
    """将秒数格式化为 MM:SS"""
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
