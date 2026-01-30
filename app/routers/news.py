"""新闻快讯 API 路由"""
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.common import ApiResponse
from app.models.news import NewsArticleListItem, NewsArticleDetail, PaginatedNews
from app.models.db_models import NewsArticle as NewsArticleORM
from app.database import get_db
from app.services.news_service import NewsService, fetch_all_sources_and_save, translate_missing_zh
from app.utils.logger import logger

router = APIRouter()


def _to_list_item(orm: NewsArticleORM, lang: str = "en") -> NewsArticleListItem:
    use_zh = (lang or "").lower() in ("zh", "zh-cn", "zh_cn")
    title = (orm.title_zh or orm.title) if use_zh else orm.title
    summary = (orm.summary_zh or orm.summary) if use_zh else orm.summary
    return NewsArticleListItem(
        id=orm.id,
        source_name=orm.source_name,
        title=title or orm.title,
        summary=summary,
        url=orm.url,
        published_at=orm.published_at,
        created_at=orm.created_at,
    )


def _to_detail(orm: NewsArticleORM, lang: str = "en") -> NewsArticleDetail:
    use_zh = (lang or "").lower() in ("zh", "zh-cn", "zh_cn")
    title = (orm.title_zh or orm.title) if use_zh else orm.title
    summary = (orm.summary_zh or orm.summary) if use_zh else orm.summary
    content = (orm.content_zh or orm.content) if use_zh else orm.content
    return NewsArticleDetail(
        id=orm.id,
        source_name=orm.source_name,
        title=title or orm.title,
        summary=summary,
        url=orm.url,
        published_at=orm.published_at,
        created_at=orm.created_at,
        content=content,
    )


@router.get("/news", response_model=ApiResponse[dict])
async def list_news(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    lang: str = Query(default="en", description="语言：en 英文，zh 中文"),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    新闻快讯列表（分页），供前端下拉刷新/分页加载。
    需要中文时请传 lang=zh（如 /api/v1/news?lang=zh）；若仍为英文说明该条尚未翻译，可调 POST /api/v1/news/translate 回填。
    """
    if db is None:
        raise HTTPException(status_code=503, detail="数据库未连接，新闻功能不可用")
    svc = NewsService(db)
    items, total = await svc.list_articles(page=page, page_size=page_size)
    list_items = [_to_list_item(o, lang=lang) for o in items]
    data = PaginatedNews(items=list_items, total=total, page=page, page_size=page_size)
    return ApiResponse.success(data=data.model_dump(), message="获取成功")


@router.get("/news/refresh")
async def refresh_news_get_method_not_allowed():
    """刷新新闻请使用 POST /api/v1/news/refresh，GET 会返回 405。"""
    raise HTTPException(
        status_code=405,
        detail="请使用 POST 方法调用刷新接口：POST /api/v1/news/refresh",
    )


@router.get("/news/translate")
async def translate_get_method_not_allowed():
    """翻译回填请使用 POST /api/v1/news/translate，GET 会返回 405。"""
    raise HTTPException(
        status_code=405,
        detail="请使用 POST 方法调用翻译回填接口：POST /api/v1/news/translate",
    )


@router.get("/news/{article_id}", response_model=ApiResponse[dict])
async def get_news_detail(
    article_id: int,
    lang: str = Query(default="en", description="语言：en 英文，zh 中文"),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """新闻详情（含正文），lang=zh 时返回中文标题/摘要/正文（若已翻译）"""
    if db is None:
        raise HTTPException(status_code=503, detail="数据库未连接，新闻功能不可用")
    svc = NewsService(db)
    article = await svc.get_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="新闻不存在")
    return ApiResponse.success(data=_to_detail(article, lang=lang).model_dump(), message="获取成功")


@router.post("/news/refresh", response_model=ApiResponse[dict])
async def refresh_news(db: Optional[AsyncSession] = Depends(get_db)):
    """
    从配置的数据源拉取最新新闻并写入数据库（含自动翻译中文）。
    前端下拉刷新时也可先调此接口再调列表接口，以拿到最新数据。
    """
    if db is None:
        raise HTTPException(status_code=503, detail="数据库未连接，新闻功能不可用")
    try:
        count = await fetch_all_sources_and_save(db)
        return ApiResponse.success(data={"count": count}, message=f"已拉取并写入 {count} 条")
    except Exception as e:
        logger.exception("新闻拉取失败")
        raise HTTPException(status_code=500, detail=f"拉取失败: {e}")


@router.post("/news/translate", response_model=ApiResponse[dict])
async def backfill_news_translate(
    limit: int = Query(default=50, ge=1, le=200, description="最多翻译条数（未填中文的记录）"),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    对库中尚未有中文的新闻做翻译回填。调完后用 GET /api/v1/news?lang=zh 即可看到中文。
    """
    if db is None:
        raise HTTPException(status_code=503, detail="数据库未连接，新闻功能不可用")
    try:
        count = await translate_missing_zh(db, limit=limit)
        return ApiResponse.success(data={"translated": count}, message=f"已回填翻译 {count} 条")
    except Exception as e:
        logger.exception("新闻翻译回填失败")
        raise HTTPException(status_code=500, detail=f"翻译回填失败: {e}")
