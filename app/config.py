"""配置管理模块"""
from pydantic_settings import BaseSettings
from typing import Dict, Any, List
import json


def _default_news_sources() -> List[Dict[str, Any]]:
    """默认新闻数据源：2 个（API + RSS）"""
    return [
        {
            "type": "api",
            "name": "CryptoCompare",
            "url": "https://min-api.cryptocompare.com/data/v2/news/?lang=EN",
            "response_path": "Data",
        },
        {
            "type": "rss",
            "name": "CoinDesk",
            "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        },
    ]


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用配置
    app_name: str = "Exchange API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Toobit API配置
    toobit_base_url: str = "https://api.toobit.com"
    toobit_timeout: int = 10
    toobit_retry_count: int = 3
    # Toobit WebSocket 行情推送 baseurl: wss://stream.toobit.com，路径 /quote/ws/v1
    toobit_ws_url: str = "wss://stream.toobit.com/quote/ws/v1"
    toobit_ws_ssl_verify: bool = True  # 设为 False 可跳过 SSL 校验（仅限本地/开发环境）
    toobit_ws_ping_interval: int = 60  # 心跳 ping 间隔（秒），服务端 5 分钟无 ping 会断连
    
    # 币安 API 配置（现货）
    binance_base_url: str = "https://api.binance.com"
    binance_timeout: int = 10
    binance_retry_count: int = 3

    # 币安 U 本位合约 API 配置（fapi）
    binance_usdm_base_url: str = "https://fapi.binance.com"
    binance_usdm_timeout: int = 10
    binance_usdm_retry_count: int = 3

    # 币安 币本位合约 API 配置（dapi）
    binance_coinm_base_url: str = "https://dapi.binance.com"
    binance_coinm_timeout: int = 10
    binance_coinm_retry_count: int = 3
    
    # 日志配置
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    
    # 数据库配置
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "exchange_api"
    db_charset: str = "utf8mb4"
    
    # 缓存配置
    cache_ttl: int = 86400  # 缓存过期时间（秒），默认1天（24小时）

    # 新闻快讯数据源（JSON 数组，可覆盖默认 2 个）
    # 每项: {"type":"api","name":"xxx","url":"...","response_path":"Data"} 或 {"type":"rss","name":"xxx","url":"..."}
    news_sources: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 全局配置实例
settings = Settings()


def get_news_sources() -> List[Dict[str, Any]]:
    """获取新闻数据源列表（支持 .env 中 NEWS_SOURCES JSON 覆盖默认）"""
    if settings.news_sources and settings.news_sources.strip():
        try:
            return json.loads(settings.news_sources)
        except json.JSONDecodeError:
            pass
    return _default_news_sources()


def get_exchange_config(exchange_name: str) -> Dict[str, Any]:
    """获取指定交易所的配置"""
    configs = {
        "toobit": {
            "base_url": settings.toobit_base_url,
            "timeout": settings.toobit_timeout,
            "retry_count": settings.toobit_retry_count,
        },
        "binance": {
            "base_url": settings.binance_base_url,
            "timeout": settings.binance_timeout,
            "retry_count": settings.binance_retry_count,
        },
        "binance_usdm": {
            "base_url": settings.binance_usdm_base_url,
            "timeout": settings.binance_usdm_timeout,
            "retry_count": settings.binance_usdm_retry_count,
        },
        "binance_coinm": {
            "base_url": settings.binance_coinm_base_url,
            "timeout": settings.binance_coinm_timeout,
            "retry_count": settings.binance_coinm_retry_count,
        },
    }
    
    if exchange_name not in configs:
        raise ValueError(f"Unsupported exchange: {exchange_name}")
    
    return configs[exchange_name]
