"""市场数据API路由"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.common import ApiResponse
from app.models.market import SymbolInfo
from app.services.exchange_factory import ExchangeFactory
from app.services.cache_service import CacheService
from app.database import get_db
from app.utils.logger import logger

router = APIRouter()


@router.get("/symbols", response_model=ApiResponse[List[SymbolInfo]])
async def get_symbols(
    exchange: str = Query(default="toobit", description="交易所名称，默认toobit"),
    type: Optional[str] = Query(default=None, description="交易对类型：spot(现货) 或 contract(合约)，不传则返回全部"),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    获取币对列表（带缓存功能）
    
    Args:
        exchange: 交易所名称，默认toobit
        type: 交易对类型，可选值：spot(现货)、contract(合约)，不传则返回全部
        db: 数据库会话（依赖注入，可能为None如果数据库未连接）
        
    Returns:
        币对信息列表
    """
    try:
        # 验证type参数
        if type is not None and type not in ["spot", "contract"]:
            raise HTTPException(
                status_code=400,
                detail="type参数必须是 'spot' 或 'contract'"
            )
        
        symbols = None
        use_cache = False
        
        # 策略：先查库；若数据库没有返回有效数据，则调外部 API 并写回库
        if db is not None:
            try:
                cache_service = CacheService(db)
                symbols = await cache_service.get_symbols(exchange, type)
                use_cache = True
                # 仅当有有效数据时才视为命中缓存
                if symbols is not None and len(symbols) > 0:
                    logger.info(f"从缓存获取: exchange={exchange}, type={type}, count={len(symbols)}")
                else:
                    symbols = None  # 无数据或空列表，统一视为需调 API 并写库
            except Exception as e:
                logger.warning(f"缓存查询异常，将调外部API并写库: {e}")
                use_cache = True  # 数据库可用，后续仍可写入
                symbols = None
        
        # 数据库无有效数据时：调用外部 API，并写入数据库
        if symbols is None:
            logger.info(f"数据库无有效数据，调外部API: exchange={exchange}")
            
            exchange_instance = ExchangeFactory.create(exchange)
            symbols = await exchange_instance.get_symbols()
            
            # 数据库可用则写回库，便于下次命中缓存
            if db is not None and use_cache:
                try:
                    cache_service = CacheService(db)
                    await cache_service.save_symbols(exchange, symbols)
                    logger.info(f"已从外部API获取并写入数据库: exchange={exchange}, count={len(symbols)}")
                except Exception as e:
                    logger.warning(f"写入缓存失败: {e}")
        
        # 按 type 过滤
        if type is not None:
            symbols = [s for s in symbols if s.type == type]
        
        return ApiResponse.success(data=symbols, message="获取币对列表成功")
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"不支持的交易所: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"获取币对列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取币对列表失败: {str(e)}")


@router.get("/klines")
async def get_klines(
    symbol: str = Query(..., description="交易对符号，如BTC_USDT"),
    interval: str = Query(..., description="K线周期，如1h"),
    limit: int = Query(default=100, description="返回数据条数"),
    exchange: str = Query(default="toobit", description="交易所名称，默认toobit")
):
    """
    获取K线数据（暂未实现）
    """
    raise HTTPException(status_code=501, detail="K线接口暂未实现")


@router.get("/depth")
async def get_depth(
    symbol: str = Query(..., description="交易对符号，如BTC_USDT"),
    limit: int = Query(default=20, description="返回深度条数"),
    exchange: str = Query(default="toobit", description="交易所名称，默认toobit")
):
    """
    获取深度数据（暂未实现）
    """
    raise HTTPException(status_code=501, detail="深度接口暂未实现")
