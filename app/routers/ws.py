"""
WebSocket 行情推送路由
- /ws: Toobit 行情（realtimes / wholeRealTime）
- /ws/ccxt: CCXT watch_tickers 多币种实时价格（binance / binance_usdm / toobit）
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws.toobit_realtimes_client import ToobitRealtimesClient
from app.services.ws.ccxt_ticker_manager import CcxtTickerManager, CCXT_WS_EXCHANGES
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


@router.websocket("/ws/cctx")
@router.websocket("/ws/ccxt")
async def ws_ccxt_tickers(websocket: WebSocket) -> None:
    """
    CCXT watch_tickers：多交易所、多币种实时价格推送，支持指定币对或全市场，区分现货/合约。

    连接后发送 JSON：
    - 指定币对: {"event": "sub", "exchange": "binance_usdm", "market_type": "contract", "symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}
    - 全市场: {"event": "sub", "exchange": "toobit", "market_type": "contract", "symbols": []} 或 "symbols": ["*"]
    - 取消: {"event": "cancel", "exchange": "binance_usdm", "market_type": "contract", "symbols": ["*"]}（全市场时 symbols 为空或 ["*"]）

    参数说明：
    - exchange: binance(现货)、binance_usdm(合约)、toobit(需配合 market_type)
    - market_type: spot(现货) 或 contract(合约)，默认 contract
    - symbols: 指定 CCXT 格式交易对；不传、[] 或 ["*"] 表示该交易所该类型下全部币对

    服务端推送: {"event": "tickers", "exchange": "...", "market_type": "spot|contract", "source": "ws|poll", "data": { symbol: { last, bid, ask, ... }, ... }, "ts": ...}
    """
    await websocket.accept()
    app = websocket.app
    manager: CcxtTickerManager = getattr(app.state, "ccxt_ticker_manager", None)
    if not manager:
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
            market_type = (msg.get("market_type") or "contract").strip().lower()
            if market_type not in ("spot", "contract"):
                market_type = "contract"
            symbols_raw = msg.get("symbols")
            if not isinstance(symbols_raw, list):
                symbols = [s for s in ([symbols_raw] if symbols_raw is not None else []) if s and str(s).strip()]
            else:
                symbols = [str(s).strip() for s in symbols_raw if s and str(s).strip()]
            # 全市场：前端传 [] 或 ["*"]，这里统一成 [] 传给 manager
            if symbols and all((str(s) or "").strip() == "*" for s in symbols):
                symbols = []
            if exchange not in CCXT_WS_EXCHANGES:
                await websocket.send_json({"event": "error", "message": f"不支持的交易所: {exchange}"})
                continue
            if ev == "sub":
                await manager.add(websocket, exchange, symbols, market_type=market_type)
                await websocket.send_json({
                    "event": "subscribed",
                    "exchange": exchange,
                    "market_type": market_type,
                    "symbols": symbols if symbols else ["*"],
                })
            elif ev == "cancel":
                if symbols or msg.get("symbols") is not None:
                    await manager.remove(websocket, exchange, symbols or [], market_type=market_type)
                else:
                    await manager.remove_connection_from_exchange(websocket, exchange)
                await websocket.send_json({
                    "event": "cancelled",
                    "exchange": exchange,
                    "market_type": market_type,
                    "symbols": symbols if symbols else ["*"],
                })
    except WebSocketDisconnect:
        logger.info("WebSocket CCXT 客户端断开")
    except Exception as e:
        logger.warning(f"WebSocket CCXT 异常: {e}")
    finally:
        await manager.remove_connection(websocket)
