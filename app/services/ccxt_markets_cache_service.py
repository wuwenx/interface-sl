"""CCXT 市场列表缓存服务：按 exchange + market_type 存简要 JSON，下次直接读库"""
from typing import List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.db_models import CcxtMarketsCache
from app.config import settings
from app.utils.logger import logger


def _normalize_precision(v: Any) -> Optional[float]:
    """将 CCXT 精度（int 小数位或 float 步长）转为 float 步长。"""
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            if isinstance(v, int) and v >= 0:
                return float(10 ** (-v)) if v else 1.0
            return float(v)
        return float(v)
    except (TypeError, ValueError):
        return None


def build_simple_market(m: dict) -> Optional[dict]:
    """
    从 CCXT 单条 market 构建简要字段：symbol, id, base, quote, type, precision(amount, price)。
    用于接口返回与入库。
    """
    try:
        symbol = m.get("symbol") or ""
        if not symbol:
            return None
        native_id = m.get("id") or (m.get("info") or {}).get("symbol") or symbol
        base = (m.get("base") or (m.get("info") or {}).get("baseAsset") or "").strip() or ""
        quote = (m.get("quote") or (m.get("info") or {}).get("quoteAsset") or "").strip() or ""
        mt = (m.get("type") or (m.get("info") or {}).get("type") or "spot").strip().lower()
        prec = m.get("precision") or {}
        amount = _normalize_precision(prec.get("amount"))
        price = _normalize_precision(prec.get("price"))
        precision = {}
        if amount is not None:
            precision["amount"] = amount
        if price is not None:
            precision["price"] = price
        return {
            "symbol": symbol,
            "id": str(native_id),
            "base": base,
            "quote": quote,
            "type": mt,
            "precision": precision,
        }
    except Exception:
        return None


class CcxtMarketsCacheService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.cache_ttl = settings.cache_ttl

    async def get_markets(
        self, exchange: str, market_type: str
    ) -> Optional[List[dict]]:
        """
        从数据库获取 CCXT 简要市场列表。
        无数据或过期时返回 None，调用方应调 CCXT API 并写库。
        """
        try:
            if self.cache_ttl <= 0:
                return None
            expire_time = datetime.utcnow() - timedelta(seconds=self.cache_ttl)
            result = await self.db.execute(
                select(CcxtMarketsCache).where(
                    CcxtMarketsCache.exchange == exchange,
                    CcxtMarketsCache.market_type == market_type,
                    CcxtMarketsCache.updated_at >= expire_time,
                )
            )
            row = result.scalars().first()
            if not row or not row.data:
                return None
            import json
            data = json.loads(row.data)
            if not isinstance(data, list):
                return None
            logger.info(f"CCXT 市场缓存命中: exchange={exchange}, market_type={market_type}, count={len(data)}")
            return data
        except Exception as e:
            logger.warning(f"CCXT 市场缓存读取失败: {e}")
            return None

    async def save_markets(
        self, exchange: str, market_type: str, items: List[dict]
    ) -> None:
        """保存 CCXT 简要市场列表到数据库（按 exchange + market_type 覆盖）。"""
        import json
        try:
            data_json = json.dumps(items, ensure_ascii=False)
            result = await self.db.execute(
                select(CcxtMarketsCache).where(
                    CcxtMarketsCache.exchange == exchange,
                    CcxtMarketsCache.market_type == market_type,
                )
            )
            row = result.scalars().first()
            if row:
                row.data = data_json
                row.updated_at = datetime.utcnow()
            else:
                self.db.add(
                    CcxtMarketsCache(
                        exchange=exchange,
                        market_type=market_type,
                        data=data_json,
                    )
                )
            await self.db.flush()
            # 不在此处 commit，由 get_db 在请求结束时统一提交，确保数据持久化
            logger.info(f"CCXT 市场缓存已 flush: exchange={exchange}, market_type={market_type}, count={len(items)}")
        except Exception as e:
            logger.exception(f"CCXT 市场缓存写入失败: exchange={exchange}, market_type={market_type}, error={e}")
            raise
