"""
订阅管理：记录 (exchange, symbol, topic) 对应的前端 WS 连接，
在收到上游推送时按订阅 fan-out 到各连接。
"""
import asyncio
from typing import Set, Tuple, Dict, Any
from fastapi import WebSocket

from app.utils.logger import logger


def _key(exchange: str, symbol: str, topic: str) -> Tuple[str, str, str]:
    return (exchange, symbol, topic)


class SubscriptionManager:
    """(exchange, symbol, topic) -> 订阅该组合的 WebSocket 连接集合"""

    def __init__(self) -> None:
        self._subs: Dict[Tuple[str, str, str], Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket, exchange: str, symbol: str, topic: str) -> None:
        """记录该连接订阅了 (exchange, symbol, topic)。"""
        async with self._lock:
            k = _key(exchange, symbol, topic)
            if k not in self._subs:
                self._subs[k] = set()
            self._subs[k].add(ws)
        logger.info(f"订阅: exchange={exchange}, symbol={symbol}, topic={topic}")

    async def remove(self, ws: WebSocket, exchange: str, symbol: str, topic: str) -> None:
        """移除该连接对 (exchange, symbol, topic) 的订阅。"""
        async with self._lock:
            k = _key(exchange, symbol, topic)
            if k in self._subs:
                self._subs[k].discard(ws)
                if not self._subs[k]:
                    del self._subs[k]

    async def remove_connection(self, ws: WebSocket) -> None:
        """连接断开时，移除该连接在所有 key 下的订阅。"""
        async with self._lock:
            to_del: list = []
            for k, conns in self._subs.items():
                conns.discard(ws)
                if not conns:
                    to_del.append(k)
            for k in to_del:
                del self._subs[k]

    def get_subscribed_symbols(self, exchange: str, topic: str) -> Set[str]:
        """返回当前已订阅的 symbol 集合（用于上游按需 sub/cancel）。"""
        symbols: Set[str] = set()
        for (ex, sym, tp), conns in self._subs.items():
            if ex == exchange and tp == topic and conns:
                symbols.add(sym)
        return symbols

    async def broadcast(self, exchange: str, symbol: str, topic: str, payload: Dict[str, Any]) -> None:
        """向所有订阅了 (exchange, symbol, topic) 的连接推送 payload。wholeRealTime 时也会推给订阅了 (exchange, \"*\", topic) 的全市场连接。"""
        k = _key(exchange, symbol, topic)
        async with self._lock:
            conns = set(self._subs.get(k, ()))
            if topic == "wholeRealTime":
                conns |= set(self._subs.get(_key(exchange, "*", topic), ()))
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.warning(f"推送失败: {e}")
