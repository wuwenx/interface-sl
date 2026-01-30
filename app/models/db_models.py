"""数据库模型"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Index
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func
from app.database import Base
import json


class CcxtMarketsCache(Base):
    """CCXT 市场列表缓存（按 exchange + market_type 存简要 JSON，减少重复请求 API）"""
    __tablename__ = "ccxt_markets_cache"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    exchange = Column(String(50), nullable=False, comment="交易所名称，如 binance_usdm, toobit")
    market_type = Column(String(20), nullable=False, comment="市场类型：spot 或 contract")
    data = Column(LONGTEXT, nullable=False, comment="简要市场列表 JSON 数组")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_ccxt_cache_exchange_type", "exchange", "market_type", unique=True),
        Index("idx_ccxt_cache_updated", "updated_at"),
    )


class NewsArticle(Base):
    """新闻快讯表（多数据源抓取后统一存储，支持中文翻译）"""
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    source_name = Column(String(64), nullable=False, comment="数据源名称，如 CryptoCompare、CoinDesk")
    title = Column(String(512), nullable=False, comment="标题")
    summary = Column(Text, nullable=True, comment="摘要")
    content = Column(LONGTEXT, nullable=True, comment="正文")
    title_zh = Column(String(512), nullable=True, comment="标题中文")
    summary_zh = Column(Text, nullable=True, comment="摘要中文")
    content_zh = Column(LONGTEXT, nullable=True, comment="正文中文")
    url = Column(String(1024), nullable=False, comment="原文链接")
    published_at = Column(DateTime, nullable=True, comment="源站发布时间")
    created_at = Column(DateTime, server_default=func.now(), comment="入库时间")

    __table_args__ = (
        Index("idx_news_url", "url", unique=True),
        Index("idx_news_published", "published_at"),
        Index("idx_news_created", "created_at"),
    )


class ExchangeSymbol(Base):
    """交易所币对信息表"""
    __tablename__ = "exchange_symbols"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    exchange = Column(String(50), nullable=False, comment="交易所名称")
    symbol = Column(String(50), nullable=False, comment="交易对符号")
    base_asset = Column(String(50), nullable=False, comment="基础资产")
    quote_asset = Column(String(50), nullable=False, comment="计价资产")
    status = Column(String(20), nullable=False, comment="交易状态")
    type = Column(String(20), nullable=False, default="spot", comment="交易对类型：spot(现货) 或 contract(合约)")
    base_asset_precision = Column(String(50), nullable=True, comment="基础资产精度")
    quote_precision = Column(String(50), nullable=True, comment="计价资产精度")
    min_price = Column(Float, nullable=True, comment="最小价格")
    max_price = Column(Float, nullable=True, comment="最大价格")
    tick_size = Column(Float, nullable=True, comment="价格精度")
    min_qty = Column(Float, nullable=True, comment="最小数量")
    max_qty = Column(Float, nullable=True, comment="最大数量")
    step_size = Column(Float, nullable=True, comment="数量精度")
    # raw_data字段保留但不使用，避免存储大量原始数据
    raw_data = Column(LONGTEXT, nullable=True, comment="原始JSON数据（已废弃，不再使用）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 创建联合唯一索引和普通索引
    __table_args__ = (
        Index("idx_exchange_symbol", "exchange", "symbol", "type", unique=True),
        Index("idx_exchange_type", "exchange", "type"),
        Index("idx_updated_at", "updated_at"),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "status": self.status,
            "type": self.type,
            "base_asset_precision": self.base_asset_precision,
            "quote_precision": self.quote_precision,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "tick_size": self.tick_size,
            "min_qty": self.min_qty,
            "max_qty": self.max_qty,
            "step_size": self.step_size,
        }
