"""
CCXT watch_tickers：多交易所、多币种实时 ticker 推送。
优先使用 ccxt.pro 的 watch_tickers（WebSocket），若无 ccxtpro 则回退为 REST 轮询。
"""
import asyncio
import time
from typing import Dict, Set, Tuple, List, Any, Optional

from fastapi import WebSocket

from app.utils.logger import logger

# 与 market 路由一致：本站 exchange 名 -> CCXT id（现货/合约共用）
CCXT_WS_EXCHANGES = {
    "binance": "binance",           # 现货
    "binance_usdm": "binanceusdm",  # 合约
    "toobit": "toobit",             # 现货+合约，由 market_type 区分
}

# 轮询间隔（无 ccxtpro 时）
POLL_INTERVAL = 2.0

# key: (exchange, market_type, frozenset(symbols))；symbols 为空或 ["*"] 表示全市场
def _key(exchange: str, market_type: str, symbols: List[str]) -> Tuple[str, str, frozenset]:
    ex = exchange.strip().lower()
    mt = (market_type or "contract").strip().lower()
    if mt not in ("spot", "contract"):
        mt = "contract"
    normalized = [s.strip() for s in symbols if s and str(s).strip() and str(s).strip() != "*"]
    return (ex, mt, frozenset(normalized) if normalized else frozenset())


def _is_all_symbols(symbols: List[str]) -> bool:
    """symbols 为空或仅含 '*' 表示订阅该交易所该类型下全部币对。"""
    if not symbols:
        return True
    return all((str(s) or "").strip() == "*" for s in symbols)


class CcxtTickerManager:
    """
    按 (exchange, market_type, symbols) 维护订阅与 watch_tickers 任务；
    支持指定 symbols 或全市场（symbols 为空/["*"]），区分现货(spot)/合约(contract)。
    """

    def __init__(self) -> None:
        self._subs: Dict[Tuple[str, str, frozenset], Set[WebSocket]] = {}
        self._tasks: Dict[Tuple[str, str, frozenset], asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def add(
        self, ws: WebSocket, exchange: str, symbols: List[str], market_type: str = "contract"
    ) -> None:
        """订阅 (exchange, market_type, symbols) 的 ticker 推送；symbols 为空或 ['*'] 表示该所该类型下全部币对。"""
        ex = exchange.strip().lower()
        if ex not in CCXT_WS_EXCHANGES:
            return
        key = _key(exchange, market_type, symbols)
        async with self._lock:
            if key not in self._subs:
                self._subs[key] = set()
            self._subs[key].add(ws)
            if key not in self._tasks or self._tasks[key].done():
                self._tasks[key] = asyncio.create_task(self._run_loop(key))
        label = "全市场" if _is_all_symbols(symbols) else list(key[2])
        logger.info(f"CCXT tickers 订阅: exchange={ex}, market_type={key[1]}, symbols={label}")

    async def remove(
        self, ws: WebSocket, exchange: str, symbols: List[str], market_type: str = "contract"
    ) -> None:
        """取消该连接对 (exchange, market_type, symbols) 的订阅。"""
        key = _key(exchange, market_type, symbols)
        async with self._lock:
            if key in self._subs:
                self._subs[key].discard(ws)
                if not self._subs[key]:
                    del self._subs[key]
                    if key in self._tasks:
                        self._tasks[key].cancel()
                        try:
                            await self._tasks[key]
                        except asyncio.CancelledError:
                            pass
                        del self._tasks[key]

    async def remove_connection(self, ws: WebSocket) -> None:
        """连接断开时移除该连接在所有 (exchange, symbols) 下的订阅并清理空任务。"""
        await self._remove_ws_from_keys(ws, exchange_filter=None)

    async def remove_connection_from_exchange(self, ws: WebSocket, exchange: str) -> None:
        """仅移除该连接在指定 exchange 下所有 symbols 的订阅。"""
        await self._remove_ws_from_keys(ws, exchange_filter=exchange.strip().lower())

    async def _remove_ws_from_keys(
        self, ws: WebSocket, exchange_filter: Optional[str] = None
    ) -> None:
        to_await: List[asyncio.Task] = []
        async with self._lock:
            for key, conns in list(self._subs.items()):
                if exchange_filter is not None and key[0] != exchange_filter:
                    continue
                conns.discard(ws)
                if not conns:
                    if key in self._tasks:
                        self._tasks[key].cancel()
                        to_await.append(self._tasks[key])
                        del self._tasks[key]
                    del self._subs[key]
        for t in to_await:
            try:
                await t
            except asyncio.CancelledError:
                pass

    async def _broadcast(
        self, key: Tuple[str, str, frozenset], tickers: Dict[str, Any], source: str = "unknown"
    ) -> None:
        """向订阅了该 key 的所有连接推送 tickers。source: ws=WebSocket(ccxt.pro)，poll=REST轮询。"""
        async with self._lock:
            conns = set(self._subs.get(key, ()))
        payload = {
            "event": "tickers",
            "exchange": key[0],
            "market_type": key[1],
            "source": source,
            "data": tickers,
            "ts": int(time.time() * 1000),
        }
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.warning(f"CCXT tickers 推送失败: {e}")

    async def _run_loop(self, key: Tuple[str, str, frozenset]) -> None:
        """对 key=(exchange, market_type, symbols) 运行 watch_tickers 或轮询；symbols 为空时从 load_markets 解析全市场。"""
        exchange, market_type, sym_set = key
        symbols = list(sym_set)
        ccxt_id = CCXT_WS_EXCHANGES.get(exchange)
        if not ccxt_id:
            return

        # 全市场：从 load_markets 按 market_type 过滤出 symbol 列表
        if not symbols:
            symbols = await self._resolve_all_symbols(ccxt_id, market_type)
            if not symbols:
                logger.warning(f"CCXT 全市场无币对: exchange={exchange} market_type={market_type}")
                return

        use_pro = False
        try:
            import ccxt.pro as ccxtpro
            ex_class = getattr(ccxtpro, ccxt_id, None)
            if ex_class:
                use_pro = True
        except ImportError:
            pass

        label = f"全市场({len(symbols)}个)" if not sym_set else str(symbols[:5]) + ("..." if len(symbols) > 5 else "")
        if use_pro:
            logger.info(
                f"CCXT tickers 数据源: WebSocket (ccxt.pro watch_tickers) | exchange={exchange} market_type={market_type} symbols={label}"
            )
            await self._run_watch_tickers_pro(key, ccxt_id, symbols)
        else:
            logger.info(
                f"CCXT tickers 数据源: REST 轮询 (fetch_tickers 每 {POLL_INTERVAL}s) | exchange={exchange} market_type={market_type} symbols={label}"
            )
            await self._run_poll_tickers(key, ccxt_id, symbols)

    async def _resolve_all_symbols(self, ccxt_id: str, market_type: str) -> List[str]:
        """加载该交易所市场并按 market_type(spot/contract) 过滤出 symbol 列表。"""
        import ccxt.async_support as ccxt
        ex_class = getattr(ccxt, ccxt_id)
        ex = ex_class({"enableRateLimit": True})
        try:
            await ex.load_markets()
            out = []
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
                    if ccxt_id == "toobit":
                        native_id = m.get("id") or sym
                        if (native_id or "").startswith("TBV_") or (native_id or "").startswith("TBV-"):
                            continue
                out.append(sym)
            return out
        finally:
            await ex.close()

    async def _run_watch_tickers_pro(
        self, key: Tuple[str, str, frozenset], ccxt_id: str, symbols: List[str]
    ) -> None:
        """使用 ccxt.pro watch_tickers 推送。"""
        import ccxt.pro as ccxtpro
        ex_class = getattr(ccxtpro, ccxt_id)
        ex = ex_class({"enableRateLimit": True})
        try:
            while True:
                try:
                    tickers = await ex.watch_tickers(symbols)
                    if tickers and isinstance(tickers, dict):
                        await self._broadcast(key, tickers, source="ws")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"CCXT Pro watch_tickers 异常: {e}")
                    await asyncio.sleep(2)
        finally:
            await ex.close()

    async def _run_poll_tickers(
        self, key: Tuple[str, str, frozenset], ccxt_id: str, symbols: List[str]
    ) -> None:
        """无 ccxt.pro 时使用 REST fetch_tickers 轮询并推送。全市场时传空列表调 fetch_tickers() 取全量。"""
        import ccxt.async_support as ccxt
        ex_class = getattr(ccxt, ccxt_id)
        ex = ex_class({"enableRateLimit": True})
        try:
            while True:
                try:
                    if symbols:
                        tickers = await ex.fetch_tickers(symbols)
                    else:
                        tickers = await ex.fetch_tickers()
                    if tickers and isinstance(tickers, dict):
                        await self._broadcast(key, tickers, source="poll")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"CCXT fetch_tickers 轮询异常: {e}")
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            await ex.close()
