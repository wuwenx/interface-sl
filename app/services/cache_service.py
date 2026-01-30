"""缓存服务"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.db_models import ExchangeSymbol
from app.models.market import SymbolInfo
from app.config import settings
from app.utils.logger import logger


class CacheService:
    """缓存服务类"""
    
    def __init__(self, db: AsyncSession):
        """
        初始化缓存服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
        self.cache_ttl = settings.cache_ttl
    
    async def get_symbols(
        self,
        exchange: str,
        symbol_type: Optional[str] = None
    ) -> Optional[List[SymbolInfo]]:
        """
        从数据库获取币对信息
        
        当以下任一情况发生时返回 None，调用方应调用外部 API 并重新写入数据库：
        - 数据库中没有该交易所的数据
        - 缓存已过期（超过 cache_ttl）
        - 查询结果为空列表
        - 查询或转换过程发生异常
        
        Args:
            exchange: 交易所名称
            symbol_type: 交易对类型，None表示获取全部
            
        Returns:
            币对信息列表；无有效数据时返回 None（此时应调 API 并写库）
        """
        try:
            # 计算过期时间（cache_ttl=0 表示不信任缓存，总是视为过期）
            expire_time = datetime.utcnow() - timedelta(seconds=self.cache_ttl)
            
            # 构建查询
            query = select(ExchangeSymbol).where(
                ExchangeSymbol.exchange == exchange,
                ExchangeSymbol.updated_at >= expire_time
            )
            
            # 如果指定了类型，添加类型过滤
            if symbol_type:
                query = query.where(ExchangeSymbol.type == symbol_type)
            
            result = await self.db.execute(query)
            symbols = result.scalars().all()
            
            # 无数据或空列表：视为“数据库没有可用数据”，返回 None，由调用方调 API 并写库
            if not symbols:
                logger.info(
                    f"数据库无有效数据，需调外部API并写库: exchange={exchange}, type={symbol_type} "
                    f"（可能原因：该 exchange+type 无缓存、或仅有 contract/spot 另一种类型、或缓存已过期）"
                )
                return None
            
            # 转换为SymbolInfo对象
            symbol_list = []
            for symbol in symbols:
                symbol_info = SymbolInfo(
                    symbol=symbol.symbol,
                    base_asset=symbol.base_asset,
                    quote_asset=symbol.quote_asset,
                    status=symbol.status,
                    type=symbol.type,
                    base_asset_precision=symbol.base_asset_precision,
                    quote_precision=symbol.quote_precision,
                    min_price=symbol.min_price,
                    max_price=symbol.max_price,
                    tick_size=symbol.tick_size,
                    min_qty=symbol.min_qty,
                    max_qty=symbol.max_qty,
                    step_size=symbol.step_size,
                )
                symbol_list.append(symbol_info)
            
            logger.info(f"从缓存获取币对信息: exchange={exchange}, type={symbol_type}, count={len(symbol_list)}")
            return symbol_list
        
        except Exception as e:
            logger.error(f"从缓存获取币对信息失败: {e}")
            return None
    
    async def save_symbols(
        self,
        exchange: str,
        symbols: List[SymbolInfo]
    ):
        """
        保存币对信息到数据库（只保存解析后的字段）
        
        Args:
            exchange: 交易所名称
            symbols: 币对信息列表
        """
        try:
            # 先删除该交易所的旧数据
            await self.db.execute(
                delete(ExchangeSymbol).where(ExchangeSymbol.exchange == exchange)
            )
            
            # 批量插入新数据（不保存原始数据）
            for symbol in symbols:
                db_symbol = ExchangeSymbol(
                    exchange=exchange,
                    symbol=symbol.symbol,
                    base_asset=symbol.base_asset,
                    quote_asset=symbol.quote_asset,
                    status=symbol.status,
                    type=symbol.type,
                    base_asset_precision=symbol.base_asset_precision,
                    quote_precision=symbol.quote_precision,
                    min_price=symbol.min_price,
                    max_price=symbol.max_price,
                    tick_size=symbol.tick_size,
                    min_qty=symbol.min_qty,
                    max_qty=symbol.max_qty,
                    step_size=symbol.step_size,
                    raw_data=None,  # 不保存原始数据
                )
                self.db.add(db_symbol)
            
            await self.db.commit()
            logger.info(f"保存币对信息到缓存: exchange={exchange}, count={len(symbols)}")
        
        except Exception as e:
            await self.db.rollback()
            logger.error(f"保存币对信息到缓存失败: {e}")
            raise
    
    async def clear_cache(self, exchange: str):
        """
        清除指定交易所的缓存
        
        Args:
            exchange: 交易所名称
        """
        try:
            await self.db.execute(
                delete(ExchangeSymbol).where(ExchangeSymbol.exchange == exchange)
            )
            await self.db.commit()
            logger.info(f"清除缓存: exchange={exchange}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"清除缓存失败: {e}")
            raise
