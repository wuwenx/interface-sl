"""FastAPI应用入口"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.routers import market, ws, news
from app.database import init_db, close_db
from app.utils.logger import logger
from app.models.common import ApiResponse
from app.services.ws.subscription import SubscriptionManager
from app.services.ws.toobit_realtimes_client import ToobitRealtimesClient
from app.services.ws.ccxt_ticker_manager import CcxtTickerManager

# 创建FastAPI应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="多交易所API统一接口服务",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(market.router, prefix="/api/v1", tags=["市场数据"])
app.include_router(ws.router, prefix="", tags=["WebSocket"])
app.include_router(news.router, prefix="/api/v1", tags=["新闻快讯"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ApiResponse.error(
            code=500,
            message="服务器内部错误",
            data=None
        ).dict()
    )


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info(f"{settings.app_name} v{settings.app_version} 启动成功")
    logger.info(f"API文档地址: http://{settings.host}:{settings.port}/docs")
    
    # 初始化数据库（可选，失败不影响服务启动）
    try:
        from app.database import init_database_engine, init_db, migrate_news_zh_columns
        init_database_engine()
        await init_db()
        await migrate_news_zh_columns()
        logger.info("数据库连接成功，缓存功能已启用")
    except Exception as e:
        logger.warning(f"数据库初始化失败（缓存功能将不可用）: {e}")
        logger.warning("请检查数据库配置和连接，服务将继续运行但无法使用缓存功能")

    # WebSocket 行情：订阅管理 + Toobit 客户端（现货 realtimes / 合约 wholeRealTime）
    sub_mgr = SubscriptionManager()
    async def on_ticker(sym: str, topic: str, msg: dict):
        await sub_mgr.broadcast(
            "toobit", sym, topic,
            {"event": topic, "exchange": "toobit", "symbol": sym, "data": msg.get("data"), "sendTime": msg.get("sendTime"), "f": msg.get("f")},
        )
    toobit_client = ToobitRealtimesClient(on_ticker=on_ticker)
    toobit_client.start()
    app.state.subscription_manager = sub_mgr
    app.state.toobit_realtimes = toobit_client
    app.state.ccxt_ticker_manager = CcxtTickerManager()
    logger.info("Toobit realtimes WS 客户端已启动")
    logger.info("CCXT watch_tickers WS 已就绪: /api/v1/ws/ccxt")

    # 新闻快讯：启动时拉取一次，便于首屏有数据
    try:
        from app.database import AsyncSessionLocal
        from app.services.news_service import fetch_all_sources_and_save
        async def _first_news_fetch():
            try:
                async with AsyncSessionLocal() as session:
                    n = await fetch_all_sources_and_save(session)
                    await session.commit()
                    logger.info(f"新闻快讯首次拉取完成，写入 {n} 条")
            except Exception as e:
                logger.warning(f"新闻快讯首次拉取失败: {e}")
        import asyncio
        asyncio.create_task(_first_news_fetch())
    except Exception as e:
        logger.warning(f"新闻快讯启动拉取未执行: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info(f"{settings.app_name} 正在关闭...")
    if hasattr(app.state, "toobit_realtimes") and app.state.toobit_realtimes is not None:
        await app.state.toobit_realtimes.stop()
        logger.info("Toobit realtimes WS 客户端已停止")
    await close_db()


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}
