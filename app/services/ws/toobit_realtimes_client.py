"""
Toobit WebSocket 客户端：按 Symbol 的完整 Ticker
- 现货 topic: realtimes
- 合约 topic: wholeRealTime
"""
import asyncio
import json
import ssl
import time
from typing import Set, Callable, Awaitable, Optional, Any, Tuple

import certifi
import websockets

from app.config import settings
from app.utils.logger import logger

TOOBIT_WS_URL = getattr(settings, "toobit_ws_url", "wss://stream.toobit.com/quote/ws/v1")
# 心跳：按 Toobit 文档 https://api-docs.toobit.com/zh/api/spot-websocket-market-data.html#%E5%BF%83%E8%B7%B3
# 客户端需定期发送 ping 帧 {"ping": timestamp}，服务端回复 pong 帧，否则 5 分钟内断连
PING_INTERVAL = getattr(settings, "toobit_ws_ping_interval", 60)
FIRST_PING_DELAY = 15  # 连接后 15 秒发首包 ping，避免服务端空闲超时
RECONNECT_DELAY = 5

# 支持的 topic：现货 realtimes，合约 wholeRealTime
TOOBIT_TOPICS = frozenset({"realtimes", "wholeRealTime"})


def _sub_message(symbol: str, topic: str) -> dict:
    """构建发给 Toobit 的 sub 报文。wholeRealTime 全市场按文档只发 topic+event，与直接连 Toobit 可推送的格式一致。"""
    if topic == "wholeRealTime":
        return {"topic": "wholeRealTime", "event": "sub"}
    return {
        "symbol": symbol,
        "topic": topic,
        "event": "sub",
        "params": {"realtimeInterval": "24h", "binary": False},
    }


def _cancel_message(symbol: str, topic: str) -> dict:
    """构建发给 Toobit 的 cancel 报文。wholeRealTime 只发 topic+event。"""
    if topic == "wholeRealTime":
        return {"topic": "wholeRealTime", "event": "cancel"}
    return {
        "symbol": symbol,
        "topic": topic,
        "event": "cancel",
        "params": {"realtimeInterval": "24h", "binary": False},
    }


class ToobitRealtimesClient:
    """
    连接 Toobit WS，订阅 realtimes（现货）或 wholeRealTime（合约），
    收到推送时通过 on_ticker(symbol, topic, payload) 回调给上游。
    """

    def __init__(
        self,
        on_ticker: Callable[[str, str, dict], Awaitable[None]],
        url: Optional[str] = None,
    ):
        self._url = url or TOOBIT_WS_URL
        self._on_ticker = on_ticker
        self._subscribed: Set[Tuple[str, str]] = set()  # (symbol, topic)
        self._whole_realtime_subscribed: bool = False  # wholeRealTime 全市场只向 Toobit 发一次 sub
        self._ws: Any = None
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def ensure_subscribe(self, symbol: str, topic: str = "realtimes") -> None:
        """确保已订阅该 symbol 的 topic。realtimes 按 symbol 订阅；wholeRealTime 为全市场，只向 Toobit 发一次 sub。"""
        if topic not in TOOBIT_TOPICS:
            return
        key = (symbol, topic)
        async with self._lock:
            if key in self._subscribed:
                return
            self._subscribed.add(key)
        if self._ws and self._ws.open:
            try:
                if topic == "wholeRealTime":
                    if not self._whole_realtime_subscribed:
                        await self._ws.send(json.dumps(_sub_message("", topic)))
                        self._whole_realtime_subscribed = True
                        logger.info("Toobit wholeRealTime（全市场）已订阅")
                else:
                    await self._ws.send(json.dumps(_sub_message(symbol, topic)))
                    logger.info(f"Toobit {topic} 已订阅: {symbol}")
            except Exception as e:
                logger.warning(f"Toobit 发送 sub 失败 {symbol} {topic}: {e}")
                async with self._lock:
                    self._subscribed.discard(key)
                if topic == "wholeRealTime":
                    self._whole_realtime_subscribed = False

    async def ensure_unsubscribe(self, symbol: str, topic: str = "realtimes") -> None:
        """取消订阅该 symbol 的 topic。wholeRealTime 在所有客户端都取消该 topic 后，才向 Toobit 发 cancel。"""
        if topic not in TOOBIT_TOPICS:
            return
        key = (symbol, topic)
        async with self._lock:
            if key not in self._subscribed:
                return
            self._subscribed.discard(key)
            still_whole = any(t == "wholeRealTime" for (_, t) in self._subscribed)
        if self._ws and self._ws.open:
            try:
                if topic == "wholeRealTime" and not still_whole:
                    await self._ws.send(json.dumps(_cancel_message("", topic)))
                    self._whole_realtime_subscribed = False
                    logger.info("Toobit wholeRealTime（全市场）已取消")
                elif topic != "wholeRealTime":
                    await self._ws.send(json.dumps(_cancel_message(symbol, topic)))
                    logger.info(f"Toobit {topic} 已取消: {symbol}")
            except Exception as e:
                logger.warning(f"Toobit 发送 cancel 失败 {symbol} {topic}: {e}")

    def _get_snapshot(self) -> Set[Tuple[str, str]]:
        """当前已订阅的 (symbol, topic) 快照（用于重连后重发 sub）。"""
        return set(self._subscribed)

    def _ssl_for_connect(self) -> Any:
        """返回 websockets.connect 的 ssl 参数：校验时用 certifi CA，不校验时用 False。"""
        if getattr(settings, "toobit_ws_ssl_verify", True):
            try:
                ctx = ssl.create_default_context(cafile=certifi.where())
                return ctx
            except Exception:
                return True  # 回退到默认
        return False

    async def _run(self) -> None:
        ssl_arg = self._ssl_for_connect()
        while True:
            try:
                async with websockets.connect(
                    self._url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                    max_size=None,  # 不限制消息大小，避免 wholeRealTime 全量推送被截断
                    ssl=ssl_arg,
                ) as ws:
                    self._ws = ws
                    logger.info("Toobit WS 已连接")
                    # 重连后重新订阅：wholeRealTime 全市场只发一次
                    self._whole_realtime_subscribed = False
                    sent_whole = False
                    for sym, tp in self._get_snapshot():
                        if tp == "wholeRealTime":
                            if not sent_whole:
                                await ws.send(json.dumps(_sub_message("", tp)))
                                self._whole_realtime_subscribed = True
                                sent_whole = True
                        else:
                            await ws.send(json.dumps(_sub_message(sym, tp)))
                    # 启动后台 ping 任务
                    ping_task = asyncio.create_task(self._ping_loop(ws))
                    try:
                        while True:
                            raw = await ws.recv()
                            try:
                                msg = json.loads(raw) if isinstance(raw, str) else raw
                            except Exception:
                                continue
                            # 处理 Toobit 心跳 pong 响应：{"pong": timestamp}
                            if isinstance(msg, dict) and "pong" in msg:
                                continue
                            msg_topic = msg.get("topic")
                            if msg_topic in TOOBIT_TOPICS and "data" in msg:
                                data = msg.get("data")
                                if isinstance(data, dict):
                                    sym = msg.get("symbol") or data.get("s")
                                else:
                                    sym = msg.get("symbol") or (
                                        (data or [{}])[0].get("s") if data else None
                                    )
                                if sym:
                                    await self._on_ticker(sym, msg_topic, msg)
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except asyncio.CancelledError:
                            pass
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed as e:
                reason = getattr(e, "reason", None) or getattr(e, "code", None) or str(e)
                logger.warning(f"Toobit WS 连接异常断开: {reason}，{RECONNECT_DELAY} 秒后重连")
            except Exception as e:
                logger.warning(f"Toobit WS 断开或异常: {e}")
            self._ws = None
            self._whole_realtime_subscribed = False
            await asyncio.sleep(RECONNECT_DELAY)

    async def _ping_loop(self, ws: Any) -> None:
        """
        按 Toobit 文档发送心跳 ping 帧，服务端回复 pong，否则 5 分钟内断连。
        请求格式: {"ping": 1535975085052}
        响应格式: {"pong": 1535975085052}
        首包 ping 在连接后 15 秒发送，之后每 PING_INTERVAL 秒发送，避免服务端空闲超时。
        """
        first = True
        while True:
            delay = FIRST_PING_DELAY if first else PING_INTERVAL
            await asyncio.sleep(delay)
            first = False
            if not ws.open:
                return
            try:
                payload = {"ping": int(time.time() * 1000)}
                await ws.send(json.dumps(payload))
            except Exception:
                return

    def start(self) -> None:
        """在后台启动连接与收包循环。"""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """停止并关闭连接。"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._ws = None
        self._subscribed.clear()
        self._whole_realtime_subscribed = False

    @staticmethod
    def normalize_topic(topic: str) -> str:
        """将前端传入的 topic 规范为 Toobit 使用：realtimes / wholeRealTime。"""
        t = (topic or "").strip()
        if t.lower() == "wholerealtime":
            return "wholeRealTime"
        if t.lower() == "realtimes":
            return "realtimes"
        return t
