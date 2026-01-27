"""配置管理模块"""
from pydantic_settings import BaseSettings
from typing import Dict, Any


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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 全局配置实例
settings = Settings()


def get_exchange_config(exchange_name: str) -> Dict[str, Any]:
    """获取指定交易所的配置"""
    configs = {
        "toobit": {
            "base_url": settings.toobit_base_url,
            "timeout": settings.toobit_timeout,
            "retry_count": settings.toobit_retry_count,
        }
    }
    
    if exchange_name not in configs:
        raise ValueError(f"Unsupported exchange: {exchange_name}")
    
    return configs[exchange_name]
