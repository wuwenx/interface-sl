"""新闻快讯 API 模型"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class NewsArticleListItem(BaseModel):
    """列表项（摘要）"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_name: str
    title: str
    summary: Optional[str] = None
    url: str
    published_at: Optional[datetime] = None
    created_at: datetime


class NewsArticleDetail(NewsArticleListItem):
    """详情（含正文）"""
    content: Optional[str] = None


class PaginatedNews(BaseModel):
    """分页新闻列表"""
    items: List[NewsArticleListItem]
    total: int
    page: int
    page_size: int
