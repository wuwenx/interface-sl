"""
WebSocket 行情推送路由
前端连接后通过 event: sub/cancel 订阅/取消 Toobit 行情：
- 现货 topic: realtimes
- 合约 topic: wholeRealTime
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws.toobit_realtimes_client import ToobitRealtimesClient
from app.utils.logger import logger

router = APIRouter()

TOOBIT_ALLOWED_TOPICS = frozenset({"realtimes", "wholeRealTime"})


@router.websocket("/ws")
async def ws_market(websocket: WebSocket) -> None:
    """
    WebSocket 行情推送
    
    连接后发送 JSON：
    - 现货订阅: {"event":"sub","exchange":"toobit","symbol":"BTCUSDT","topic":"realtimes"}
    - 合约订阅: {"event":"sub","exchange":"toobit","topic":"wholeRealTime"} 或带 symbol；不传 symbol 表示全市场
    - 取消: {"event":"cancel","exchange":"toobit","topic":"wholeRealTime"}（不传 symbol 即取消全市场订阅）
    
    服务端推送: {"event":"realtimes"|"wholeRealTime","exchange":"toobit","symbol":"...","data":{...},"sendTime":...,"f":...}
    合约 wholeRealTime 的 data 与 GET /api/v1/ticker/24hr 单条结构兼容（含 s,c,o,h,l,v,qv 等），前端可按 symbol 或 data.s 合并更新本地 24hr 列表。
    """
    await websocket.accept()
    app = websocket.app
    sub_mgr = getattr(app.state, "subscription_manager", None)
    toobit = getattr(app.state, "toobit_realtimes", None)
    if not sub_mgr or not toobit:
        await websocket.close(code=1011)
        return
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = __import__("json").loads(raw)
            except Exception:
                continue
            ev = (msg.get("event") or "").strip().lower()
            exchange = (msg.get("exchange") or "").strip().lower()
            topic_raw = (msg.get("topic") or "").strip()
            topic = ToobitRealtimesClient.normalize_topic(topic_raw)
            symbol_raw = (msg.get("symbol") or "").strip().upper()
            # wholeRealTime 可不传 symbol，内部用 "*" 表示全市场
            if topic == "wholeRealTime" and not symbol_raw:
                symbol = "*"
            else:
                symbol = symbol_raw
            if topic not in TOOBIT_ALLOWED_TOPICS:
                continue
            if topic == "realtimes" and not symbol:
                continue
            if ev == "sub":
                if exchange == "toobit":
                    await sub_mgr.add(websocket, "toobit", symbol, topic)
                    await toobit.ensure_subscribe(symbol, topic)
                    await websocket.send_json({
                        "event": "subscribed",
                        "exchange": "toobit",
                        "symbol": symbol,
                        "topic": topic,
                    })
            elif ev == "cancel":
                if exchange == "toobit":
                    await sub_mgr.remove(websocket, "toobit", symbol, topic)
                    await toobit.ensure_unsubscribe(symbol, topic)
                    await websocket.send_json({
                        "event": "cancelled",
                        "exchange": "toobit",
                        "symbol": symbol,
                        "topic": topic,
                    })
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开")
    except Exception as e:
        logger.warning(f"WebSocket 异常: {e}")
    finally:
        await sub_mgr.remove_connection(websocket)
