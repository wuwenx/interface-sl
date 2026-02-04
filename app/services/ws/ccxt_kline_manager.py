"""
CCXT 实时 K 线推送：watch_ohlcv（WebSocket）或 fetch_ohlcv 轮询。
优先使用 ccxt.pro 的 watch_ohlcv，若无 ccxtpro 则回退为 REST 轮询。
"""
import asyncio
import time
from typing import Dict, Set, Tuple, List, Any, Optional

from fastapi import WebSocket

from app.config import settings
from app.utils.logger import logger

CCXT_WS_EXCHANGES = {
    "binance": "binance",
    "binance_usdm": "binanceusdm",
    "toobit": "toobit",
}

# REST 轮询间隔（秒），用于不支持 watchOHLCV 的交易所（如 Toobit）
POLL_INTERVAL = 10


def _key(exchange: str, symbol: str, interval: str) -> Tuple[str, str, str]:
    ex = exchange.strip().lower()
    sym = (symbol or "").strip()
    tf = (interval or "1h").strip().lower()
    return (ex, sym, tf)


def _to_kline_dict(row: list) -> dict:
    """CCXT ohlcv 行转 KlineData 兼容的 dict"""
    ts = int(row[0])
    o, h, l, c, v = float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])
    quote_vol = None
    if len(row) > 6 and row[6] is not None:
        try:
            quote_vol = float(row[6])
        except (TypeError, ValueError):
            pass
    trades = None
    if len(row) > 7 and row[7] is not None:
        try:
            trades = int(row[7])
        except (TypeError, ValueError):
            pass
    return {
        "timestamp": ts,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "quote_volume": quote_vol,
        "trades": trades,
    }


class CcxtKlineManager:
    """
    按 (exchange, symbol, interval) 维护 K 线订阅；
    支持 watch_ohlcv（ccxt.pro）或 fetch_ohlcv 轮询。
    """

    def __init__(self) -> None:
        self._subs: Dict[Tuple[str, str, str], Set[WebSocket]] = {}
        self._tasks: Dict[Tuple[str, str, str], asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def add(
        self, ws: WebSocket, exchange: str, symbol: str, interval: str = "1h"
    ) -> None:
        """订阅 (exchange, symbol, interval) 的 K 线推送。"""
        ex = exchange.strip().lower()
        if ex not in CCXT_WS_EXCHANGES:
            return
        sym = (symbol or "").strip()
        if not sym:
            return
        key = _key(exchange, symbol, interval)
        async with self._lock:
            if key not in self._subs:
                self._subs[key] = set()
            self._subs[key].add(ws)
            if key not in self._tasks or self._tasks[key].done():
                self._tasks[key] = asyncio.create_task(self._run_loop(key))
        logger.info(f"CCXT K线订阅: exchange={ex}, symbol={sym}, interval={key[2]}")

    async def remove(
        self, ws: WebSocket, exchange: str, symbol: str, interval: str = "1h"
    ) -> None:
        """取消该连接对 (exchange, symbol, interval) 的订阅。"""
        key = _key(exchange, symbol, interval)
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
        """连接断开时移除该连接在所有 key 下的订阅。"""
        to_await: List[asyncio.Task] = []
        async with self._lock:
            for key, conns in list(self._subs.items()):
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
        self, key: Tuple[str, str, str], candle: dict, source: str = "unknown"
    ) -> None:
        """向订阅了该 key 的所有连接推送单根 K 线。"""
        async with self._lock:
            conns = set(self._subs.get(key, ()))
        payload = {
            "event": "kline",
            "exchange": key[0],
            "symbol": key[1],
            "interval": key[2],
            "source": source,
            "data": candle,
            "ts": int(time.time() * 1000),
        }
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.warning(f"CCXT K线推送失败: {e}")

    def _has_ccxtpro(self, ccxt_id: str) -> bool:
        try:
            import ccxt.pro as ccxtpro
            return getattr(ccxtpro, ccxt_id, None) is not None
        except ImportError:
            return False

    async def _run_loop(self, key: Tuple[str, str, str]) -> None:
        """对 key 运行 watch_ohlcv 或轮询。若交易所不支持 watchOHLCV 则强制用 REST。"""
        exchange, symbol, interval = key
        ccxt_id = CCXT_WS_EXCHANGES.get(exchange)
        if not ccxt_id:
            return

        use_pro = self._has_ccxtpro(ccxt_id)
        if use_pro:
            # 检查该交易所是否真正支持 watchOHLCV（如 Toobit 不支持）
            supports_ws = await self._check_watch_ohlcv_support(ccxt_id)
            if supports_ws:
                logger.info(
                    f"CCXT K线数据源: WebSocket (ccxt.pro watch_ohlcv) | exchange={exchange} symbol={symbol} interval={interval}"
                )
                await self._run_watch_ohlcv_pro(key, ccxt_id)
                return
        logger.info(
            f"CCXT K线数据源: REST 轮询 (fetch_ohlcv 每 {POLL_INTERVAL}s) | exchange={exchange} symbol={symbol} interval={interval}"
        )
        await self._run_poll_ohlcv(key, ccxt_id)

    async def _check_watch_ohlcv_support(self, ccxt_id: str) -> bool:
        """检查交易所是否支持 watchOHLCV，需 load_markets 后 has 才准确。"""
        try:
            import ccxt.pro as ccxtpro
            ex_class = getattr(ccxtpro, ccxt_id, None)
            if not ex_class:
                return False
            ex = ex_class({"enableRateLimit": True, "timeout": settings.ccxt_timeout})
            try:
                await ex.load_markets()
                return bool(ex.has.get("watchOHLCV", False))
            finally:
                await ex.close()
        except Exception as e:
            logger.warning(f"检查 watchOHLCV 支持失败 {ccxt_id}: {e}")
            return False

    def _parse_ohlcv_response(self, ohlcv: Any) -> Optional[list]:
        """解析 watch_ohlcv 返回值：可能是 [ts,o,h,l,c,v] 或 [[ts,o,h,l,c,v],...]"""
        if not ohlcv or not isinstance(ohlcv, list):
            return None
        if len(ohlcv) >= 6 and isinstance(ohlcv[0], (int, float)):
            return ohlcv
        if len(ohlcv) >= 1 and isinstance(ohlcv[0], (list, tuple)) and len(ohlcv[0]) >= 6:
            return list(ohlcv[-1])
        return None

    async def _run_watch_ohlcv_pro(
        self, key: Tuple[str, str, str], ccxt_id: str
    ) -> None:
        """使用 ccxt.pro watch_ohlcv 推送。连接后先 fetch 一根当前 K 线立即推送，再 watch 后续更新。"""
        import ccxt.pro as ccxtpro
        exchange, symbol, interval = key
        ex_class = getattr(ccxtpro, ccxt_id)
        ex = ex_class({"enableRateLimit": True, "timeout": settings.ccxt_timeout})
        try:
            await ex.load_markets()
            # 连接后立即推送当前 K 线，避免用户等待整根周期（如 1h 需等 1 小时）
            try:
                ohlcv_list = await ex.fetch_ohlcv(symbol, interval, limit=2)
                if ohlcv_list and len(ohlcv_list) >= 1:
                    row = ohlcv_list[-1]
                    candle = _to_kline_dict(row)
                    await self._broadcast(key, candle, source="ws")
            except Exception as e:
                logger.warning(f"CCXT K线首次 fetch 失败: {e}")
            while True:
                try:
                    ohlcv = await ex.watch_ohlcv(symbol, interval)
                    row = self._parse_ohlcv_response(ohlcv)
                    if row:
                        candle = _to_kline_dict(row)
                        await self._broadcast(key, candle, source="ws")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"CCXT Pro watch_ohlcv 异常: {e}")
                    await asyncio.sleep(2)
        finally:
            await ex.close()

    async def _run_poll_ohlcv(
        self, key: Tuple[str, str, str], ccxt_id: str
    ) -> None:
        """使用 REST fetch_ohlcv 轮询，取最新一根 K 线推送（用于不支持 watchOHLCV 的交易所）。"""
        import ccxt.async_support as ccxt
        exchange, symbol, interval = key
        ex_class = getattr(ccxt, ccxt_id)
        ex = ex_class({"enableRateLimit": True, "timeout": settings.ccxt_timeout})
        last_ts: Optional[int] = None
        try:
            await ex.load_markets()
            while True:
                try:
                    ohlcv_list = await ex.fetch_ohlcv(symbol, interval, limit=2)
                    if ohlcv_list and len(ohlcv_list) >= 1:
                        row = ohlcv_list[-1]
                        ts = int(row[0])
                        if last_ts is None or ts != last_ts:
                            last_ts = ts
                            candle = _to_kline_dict(row)
                            await self._broadcast(key, candle, source="poll")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"CCXT fetch_ohlcv 轮询异常: {e}")
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            await ex.close()
