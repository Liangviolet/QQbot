"""B站 视频解析 — 支持 BV号、av号、完整链接、b23.tv 短链"""

import re
from dataclasses import dataclass
from typing import Optional

import httpx

# BV 号：BV + 10 位字母数字（排除易混淆字符）
BV_PATTERN = re.compile(r"(?<!\w)(BV[1-9A-HJ-NP-Za-km-z]{10})(?!\w)")
# av 号：av + 数字
AV_PATTERN = re.compile(r"(?<!\w)[aA][vV](\d{1,12})(?!\w)")
# 完整 B站视频链接：https?://www.bilibili.com/video/BVxxx
URL_PATTERN = re.compile(r"https?://(?:www\.)?bilibili\.com/video/(BV[1-9A-HJ-NP-Za-km-z]{10})")
# b23.tv 短链：https?://b23.tv/xxxxx 或 https?://b23.tv/xxxxx?xx
B23_PATTERN = re.compile(r"https?://b23\.tv/\S+")


@dataclass
class VideoInfo:
    bvid: str
    title: str
    author: str
    views: int
    cover_url: str
    duration: int  # 秒


def _find_all_bv(text: str) -> list[str]:
    """从文本中提取所有形式的 B站视频标识，统一返回 BV 号列表（去重）"""
    seen: set[str] = set()
    result: list[str] = []

    # 1. 直接从 BV 号
    for m in BV_PATTERN.finditer(text):
        bv = m.group(1)
        if bv not in seen:
            seen.add(bv)
            result.append(bv)

    # 2. 从完整 URL 提取 BV
    for m in URL_PATTERN.finditer(text):
        bv = m.group(1)
        if bv not in seen:
            seen.add(bv)
            result.append(bv)

    # 3. av 号（先记下 aid，后续统一转换）
    av_ids: list[int] = []
    for m in AV_PATTERN.finditer(text):
        aid = int(m.group(1))
        if aid not in seen:
            seen.add(str(aid))  # 临时占位防重复
            av_ids.append(aid)

    return result, av_ids


def extract_bv_ids(text: str, max_count: int = 3) -> list[str]:
    """从文本中提取 BV 号，最多 max_count 条，去重

    这是兼容性接口，仅返回 BV 号（不含 av 号等）。
    """
    bvs, _ = _find_all_bv(text)
    return bvs[:max_count]


def has_video_ref(text: str) -> bool:
    """检查文本是否包含 B站视频引用（BV号、av号、链接）"""
    if BV_PATTERN.search(text):
        return True
    if AV_PATTERN.search(text):
        return True
    if URL_PATTERN.search(text):
        return True
    if B23_PATTERN.search(text):
        return True
    return False


async def extract_all_video_ids(
    text: str,
    client: httpx.AsyncClient,
    max_count: int = 3,
) -> list[str]:
    """从文本中提取所有 B站视频标识，返回 BV 号列表。

    支持 BV号、av号、完整 URL、b23.tv 短链。
    b23.tv 短链需要 HTTP 解析重定向。
    """
    bvs, av_ids = _find_all_bv(text)
    result = list(bvs)

    # 转换 av 号 → BV 号
    for aid in av_ids:
        if len(result) >= max_count:
            break
        bv = await _aid_to_bvid(aid, client)
        if bv:
            result.append(bv)

    # 解析 b23.tv 短链
    for m in B23_PATTERN.finditer(text):
        if len(result) >= max_count:
            break
        url = m.group(0)
        bv = await _resolve_b23(url, client)
        if bv:
            result.append(bv)

    return result[:max_count]


async def _aid_to_bvid(aid: int, client: httpx.AsyncClient) -> Optional[str]:
    """通过 API 将 av 号转换为 BV 号"""
    try:
        resp = await client.get(
            f"https://api.bilibili.com/x/web-interface/view?aid={aid}",
            timeout=5.0,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            return None
        return data["data"]["bvid"]
    except Exception:
        return None


async def _resolve_b23(url: str, client: httpx.AsyncClient) -> Optional[str]:
    """解析 b23.tv 短链，从重定向地址中提取 BV 号"""
    try:
        resp = await client.get(url, timeout=5.0, follow_redirects=True)
        final_url = str(resp.url)
        m = URL_PATTERN.search(final_url)
        if m:
            return m.group(1)
        # 有些重定向可能最终页面含 BV 但不是 /video/ 路径
        m = BV_PATTERN.search(final_url)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None


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
    """将秒数格式化为 MM:SS 或 H:MM:SS"""
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
