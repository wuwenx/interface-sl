"""市场数据API路由"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import ccxt.async_support as ccxt
from app.config import settings
from app.models.common import ApiResponse
from app.models.market import SymbolInfo, ContractTicker24h, CcxtContractSymbol, CcxtMarketInfo, CcxtMarketSimple, PaginatedCcxtContracts, OrderBook, OrderBookEntry
from app.services.exchange_factory import ExchangeFactory
from app.services.cache_service import CacheService
from app.services.ccxt_markets_cache_service import CcxtMarketsCacheService, build_simple_market
from app.database import get_db
from app.utils.logger import logger

router = APIRouter()

# CCXT 交易所 id 与本站 exchange 名称映射（合约）
CCXT_CONTRACT_EXCHANGES = {
    "binance_usdm": "binanceusdm",  # Binance U 本位合约
    "toobit": "toobit",
}
# 现货：币安现货、Toobit 现货
CCXT_SPOT_EXCHANGES = {
    "binance": "binance",
    "toobit": "toobit",
}
# CCXT 交易所 id（行情/订单簿：现货 + 合约）
CCXT_EXCHANGES = {
    "binance": "binance",           # 币安现货
    "binance_usdm": "binanceusdm",  # 币安 U 本位合约
    "toobit": "toobit",
}


@router.get("/symbols", response_model=ApiResponse[List[SymbolInfo]])
async def get_symbols(
    exchange: str = Query(default="toobit", description="交易所：toobit | binance(现货) | binance_usdm(U本位合约) | binance_coinm(币本位合约)"),
    type: Optional[str] = Query(default=None, description="交易对类型：spot(现货) 或 contract(合约)，不传则返回全部"),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    获取币对列表（带缓存功能）
    
    Args:
        exchange: 交易所名称。binance=现货，binance_usdm=U本位合约，binance_coinm=币本位合约
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


@router.get("/symbols/ccxt/contracts", response_model=ApiResponse[Dict[str, PaginatedCcxtContracts]])
async def get_contract_symbols_ccxt(
    exchange: str = Query(
        default="binance_usdm,toobit",
        description="交易所，逗号分隔。现货: binance, toobit；合约: binance_usdm, toobit",
    ),
    market_type: str = Query(
        default="contract",
        description="市场类型：spot(现货) 或 contract(合约)",
    ),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=10, ge=1, le=100, description="每页条数，默认 10"),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    获取交易对列表（简要字段：symbol、id、base、quote、type、precision），支持现货/合约与分页。
    优先从数据库缓存读取，无缓存或过期时调 CCXT API 并写入缓存；Toobit 合约会过滤 TBV_/TBV-。
    """
    if market_type not in ("spot", "contract"):
        raise HTTPException(status_code=400, detail="market_type 必须是 spot 或 contract")
    names = [x.strip().lower() for x in exchange.split(",") if x.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="请至少指定一个交易所")
    exchange_map = CCXT_SPOT_EXCHANGES if market_type == "spot" else CCXT_CONTRACT_EXCHANGES
    for n in names:
        if n not in exchange_map:
            raise HTTPException(
                status_code=400,
                detail=f"market_type={market_type} 下不支持的交易所: {n}，可选: {list(exchange_map.keys())}",
            )

    result: Dict[str, PaginatedCcxtContracts] = {}
    for our_name in names:
        simple_list: List[dict] = []
        if db is not None:
            try:
                cache_svc = CcxtMarketsCacheService(db)
                simple_list = await cache_svc.get_markets(our_name, market_type) or []
            except Exception as e:
                logger.warning(f"CCXT 缓存读取失败 {our_name}: {e}")
                simple_list = []

        if not simple_list:
            ccxt_id = exchange_map[our_name]
            try:
                ex = getattr(ccxt, ccxt_id)({"enableRateLimit": True})
                try:
                    await ex.load_markets()
                    for sym, m in ex.markets.items():
                        if not m.get("active", True):
                            continue
                        mt = (m.get("type") or "").lower()
                        if market_type == "spot":
                            if mt != "spot" or m.get("contract"):
                                continue
                        else:
                            if not m.get("contract") and mt not in ("future", "swap"):
                                continue
                            native_id = m.get("id") or sym
                            if our_name == "toobit":
                                if (native_id or "").startswith("TBV_") or (native_id or "").startswith("TBV-"):
                                    continue
                        one = build_simple_market(m)
                        if one:
                            simple_list.append(one)
                    if simple_list:
                        if db is not None:
                            try:
                                cache_svc = CcxtMarketsCacheService(db)
                                await cache_svc.save_markets(our_name, market_type, simple_list)
                            except Exception as e:
                                logger.exception(f"CCXT 缓存写入失败 {our_name}: {e}")
                                raise HTTPException(status_code=500, detail=f"写入缓存失败: {e}")
                        else:
                            logger.warning("数据库未连接，CCXT 市场列表未写入缓存，请检查 DB 配置")
                finally:
                    await ex.close()
            except Exception as e:
                logger.warning(f"CCXT fetch_markets 失败 {our_name}: {e}")
                raise HTTPException(status_code=502, detail=f"获取 {our_name} 列表失败: {e}")

        total = len(simple_list)
        start = (page - 1) * page_size
        slice_raw = simple_list[start : start + page_size]
        items = [CcxtMarketSimple(**x) for x in slice_raw]
        result[our_name] = PaginatedCcxtContracts(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
        logger.info(f"CCXT {market_type}: {our_name} 共 {total} 个，第 {page} 页 {len(items)} 条")

    return ApiResponse.success(data=result, message="获取交易对列表成功")


@router.get("/ticker/24hr", response_model=ApiResponse[List[ContractTicker24h]])
async def get_ticker_24hr(
    exchange: str = Query(default="toobit", description="交易所，当前仅支持 toobit"),
    type: str = Query(default="contract", description="类型：spot(现货) 或 contract(合约)"),
    symbol: Optional[str] = Query(default=None, description="交易对，仅现货支持；不传则返回全量"),
):
    """
    获取 24 小时价格变动数据（Toobit 现货 / 合约）
    
    - type=spot: 调用 /quote/v1/ticker/24hr，可选 symbol 过滤
    - type=contract: 调用 /quote/v1/contract/ticker/24hr，全量
    
    前端可先调此接口拿到全量列表用于展示，再通过 WebSocket 订阅 topic=wholeRealTime 实时更新交易量、最新价等。
    WS 推送格式与单条结构一致，按 data.s（或 symbol）合并到本地列表即可。
    """
    if exchange != "toobit":
        raise HTTPException(status_code=400, detail="当前仅支持 exchange=toobit")
    if type not in ("spot", "contract"):
        raise HTTPException(status_code=400, detail="type 必须是 spot 或 contract")

    if type == "spot":
        url = f"{settings.toobit_base_url.rstrip('/')}/quote/v1/ticker/24hr"
        params = {"symbol": symbol} if symbol else {}
    else:
        if symbol:
            raise HTTPException(status_code=400, detail="合约 24hr 不支持 symbol 参数")
        url = f"{settings.toobit_base_url.rstrip('/')}/quote/v1/contract/ticker/24hr"
        params = {}

    try:
        async with httpx.AsyncClient(timeout=settings.toobit_timeout) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            raw = r.json()
    except httpx.HTTPStatusError as e:
        logger.warning(f"Toobit {type} 24hr 请求失败: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=502, detail="上游 Toobit 返回错误")
    except Exception as e:
        logger.warning(f"Toobit {type} 24hr 请求异常: {e}")
        raise HTTPException(status_code=502, detail="请求 Toobit 失败")

    if not isinstance(raw, list):
        raw = [raw] if raw else []
    # 合约 24hr 过滤掉 TBV_ / TBV- 开头的交易对（与 exchangeInfo 过滤一致）
    def _skip_tbv(item: dict) -> bool:
        s = (item.get("s") or "").strip()
        return s.startswith("TBV_") or s.startswith("TBV-")
    items = [x for x in raw if isinstance(x, dict) and (type != "contract" or not _skip_tbv(x))]
    out: List[ContractTicker24h] = [ContractTicker24h.model_validate(x) for x in items]
    return ApiResponse.success(data=out, message=f"获取{type} 24hr 成功")


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


@router.get("/depth/ccxt", response_model=ApiResponse[OrderBook])
async def get_depth_ccxt(
    exchange: str = Query(
        default="toobit",
        description="交易所：binance(现货) | binance_usdm(U本位合约) | toobit",
    ),
    symbol: str = Query(
        ...,
        description="CCXT 统一交易对，现货如 BTC/USDT，合约如 BTC/USDT:USDT",
    ),
    limit: int = Query(default=20, ge=5, le=500, description="买卖盘档位数量，默认 20"),
):
    """
    使用 CCXT 获取行情订单簿（深度）。
    支持币安现货、币安 U 本位合约、Toobit；symbol 使用 CCXT 统一格式。
    """
    ex_name = exchange.strip().lower()
    if ex_name not in CCXT_EXCHANGES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的交易所: {exchange}，可选: {list(CCXT_EXCHANGES.keys())}",
        )
    ccxt_id = CCXT_EXCHANGES[ex_name]
    ex = getattr(ccxt, ccxt_id)({"enableRateLimit": True})
    try:
        await ex.load_markets()
        ob = await ex.fetch_order_book(symbol.strip(), limit)
        await ex.close()
    except Exception as e:
        await ex.close()
        logger.warning(f"CCXT 订单簿请求失败 {ex_name} {symbol}: {e}")
        raise HTTPException(status_code=502, detail=f"获取订单簿失败: {e}")

    # CCXT: bids/asks 为 [[price, amount], ...]，转为 OrderBookEntry
    def to_entries(rows: list) -> List[OrderBookEntry]:
        return [OrderBookEntry(price=float(p), quantity=float(q)) for p, q in (rows or [])]

    data = OrderBook(
        symbol=symbol,
        bids=to_entries(ob.get("bids") or []),
        asks=to_entries(ob.get("asks") or []),
        timestamp=ob.get("timestamp"),
    )
    return ApiResponse.success(data=data, message="获取订单簿成功")


@router.get("/depth")
async def get_depth(
    symbol: str = Query(..., description="交易对符号，如BTC_USDT"),
    limit: int = Query(default=20, description="返回深度条数"),
    exchange: str = Query(default="toobit", description="交易所名称，默认toobit")
):
    """
    获取深度数据（暂未实现，请使用 /depth/ccxt）
    """
    raise HTTPException(status_code=501, detail="请使用 GET /api/v1/depth/ccxt?exchange=...&symbol=...")
