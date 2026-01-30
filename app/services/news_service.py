"""新闻快讯服务：从可配置数据源（API/RSS）抓取并入库，提供列表与详情，支持中文翻译"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import httpx
import feedparser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.db_models import NewsArticle
from app.config import get_news_sources
from app.utils.logger import logger

# 单次翻译长度上限（Google 约 5000 字符）
_TRANSLATE_CHUNK = 4500


def _translate_to_chinese(text: Optional[str]) -> Optional[str]:
    """将英文文本翻译成中文，失败或空则返回 None。"""
    if not text or not str(text).strip():
        return None
    try:
        from deep_translator import GoogleTranslator
        s = str(text).strip()
        if len(s) <= _TRANSLATE_CHUNK:
            return GoogleTranslator(source="auto", target="zh-CN").translate(s)
        parts = []
        for i in range(0, len(s), _TRANSLATE_CHUNK):
            chunk = s[i : i + _TRANSLATE_CHUNK]
            parts.append(GoogleTranslator(source="auto", target="zh-CN").translate(chunk))
        return "".join(parts)
    except Exception as e:
        logger.debug(f"翻译失败: {e}")
        return None


def _parse_published_time(ts: Any) -> Optional[datetime]:
    """将时间戳或日期字符串转为 datetime"""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.utcfromtimestamp(int(ts))
        s = str(ts).strip()
        if s.isdigit():
            return datetime.utcfromtimestamp(int(s))
        # 尝试常见格式
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
            try:
                return datetime.strptime(s.replace("Z", "+00:00"), fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


async def _fetch_api(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 API 数据源拉取"""
    url = source.get("url") or ""
    path = source.get("response_path") or "Data"
    name = source.get("name") or "API"
    if not url:
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        raw = data
        for key in path.split("."):
            raw = raw.get(key) if isinstance(raw, dict) else None
            if raw is None:
                break
        if not isinstance(raw, list):
            return []
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or item.get("headline") or "").strip()
            url_str = (item.get("url") or item.get("link") or "").strip()
            if not title or not url_str:
                continue
            body = item.get("body") or item.get("summary") or item.get("description") or ""
            summary = (item.get("summary") or item.get("body") or "")[:500] if isinstance(body, str) else ""
            published = item.get("published_on") or item.get("published") or item.get("pubDate") or item.get("created_at")
            out.append({
                "source_name": name,
                "title": title,
                "summary": (summary or body[:500] if body else "")[:2000],
                "content": body[:50000] if isinstance(body, str) else None,
                "url": url_str,
                "published_at": _parse_published_time(published),
            })
        logger.info(f"新闻源 {name} API 拉取到 {len(out)} 条")
        return out
    except Exception as e:
        logger.warning(f"新闻源 {name} API 拉取失败: {e}")
        return []


def _fetch_rss_sync(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 RSS 数据源拉取（feedparser 同步）"""
    url = source.get("url") or ""
    name = source.get("name") or "RSS"
    if not url:
        return []
    try:
        feed = feedparser.parse(url)
        entries = getattr(feed, "entries", []) or []
        out = []
        for e in entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link:
                continue
            summary = (e.get("summary") or "").strip()[:2000]
            content = summary
            if hasattr(e, "content") and e.content:
                content = (e.content[0].get("value") if e.content else "")[:50000] or summary
            published = e.get("published") or e.get("updated")
            out.append({
                "source_name": name,
                "title": title,
                "summary": summary or None,
                "content": content or None,
                "url": link,
                "published_at": _parse_published_time(published),
            })
        logger.info(f"新闻源 {name} RSS 拉取到 {len(out)} 条")
        return out
    except Exception as e:
        logger.warning(f"新闻源 {name} RSS 拉取失败: {e}")
        return []


async def fetch_all_sources_and_save(db: AsyncSession) -> int:
    """
    从所有配置的数据源拉取新闻并写入数据库（按 url 去重，已存在则更新）。
    返回本次新增/更新的条数。
    """
    sources = get_news_sources()
    all_items: List[Dict[str, Any]] = []
    for src in sources:
        stype = (src.get("type") or "api").lower()
        if stype == "rss":
            items = _fetch_rss_sync(src)
        else:
            items = await _fetch_api(src)
        all_items.extend(items)

    if not all_items:
        return 0

    saved = 0
    for item in all_items:
        try:
            title_zh = _translate_to_chinese(item.get("title"))
            summary_zh = _translate_to_chinese(item.get("summary"))
            content_zh = _translate_to_chinese(item.get("content"))
            item["title_zh"] = title_zh
            item["summary_zh"] = summary_zh
            item["content_zh"] = content_zh

            result = await db.execute(
                select(NewsArticle).where(NewsArticle.url == item["url"])
            )
            row = result.scalars().first()
            if row:
                row.title = item["title"]
                row.summary = item.get("summary")
                row.content = item.get("content")
                row.title_zh = item.get("title_zh")
                row.summary_zh = item.get("summary_zh")
                row.content_zh = item.get("content_zh")
                row.source_name = item["source_name"]
                row.published_at = item.get("published_at")
            else:
                db.add(NewsArticle(
                    source_name=item["source_name"],
                    title=item["title"],
                    summary=item.get("summary"),
                    content=item.get("content"),
                    title_zh=item.get("title_zh"),
                    summary_zh=item.get("summary_zh"),
                    content_zh=item.get("content_zh"),
                    url=item["url"],
                    published_at=item.get("published_at"),
                ))
            saved += 1
        except Exception as e:
            logger.warning(f"新闻入库失败 url={item.get('url')}: {e}")
    await db.flush()
    logger.info(f"新闻快讯拉取完成，共处理 {saved} 条")
    return saved


class NewsService:
    """新闻列表与详情查询"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_articles(
        self, page: int = 1, page_size: int = 20
    ) -> Tuple[List[NewsArticle], int]:
        """分页列表，按发布时间倒序。返回 (items, total)"""
        # MySQL/MariaDB 不支持 NULLS LAST，DESC 时 NULL 默认排最后
        q = select(NewsArticle).order_by(NewsArticle.published_at.desc(), NewsArticle.created_at.desc())
        total_result = await self.db.execute(
            select(func.count()).select_from(NewsArticle)
        )
        total = total_result.scalar() or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(q.offset(offset).limit(page_size))
        items = list(result.scalars().all())
        return items, total

    async def get_by_id(self, article_id: int) -> Optional[NewsArticle]:
        """按 id 查详情"""
        result = await self.db.execute(select(NewsArticle).where(NewsArticle.id == article_id))
        return result.scalars().first()


async def translate_missing_zh(db: AsyncSession, limit: int = 50) -> int:
    """
    对库中尚未有中文翻译的新闻进行翻译回填（title_zh 为空的记录）。
    返回本次翻译条数。
    """
    result = await db.execute(
        select(NewsArticle).where(NewsArticle.title_zh.is_(None)).order_by(NewsArticle.id.desc()).limit(limit)
    )
    rows = list(result.scalars().all())
    if not rows:
        return 0
    translated = 0
    for row in rows:
        if not row.title:
            continue
        try:
            row.title_zh = _translate_to_chinese(row.title)
            row.summary_zh = _translate_to_chinese(row.summary)
            row.content_zh = _translate_to_chinese(row.content)
            translated += 1
        except Exception as e:
            logger.warning(f"翻译回填失败 id={row.id}: {e}")
    await db.flush()
    logger.info(f"新闻翻译回填完成，本次 {translated} 条")
    return translated
