"""交易所工厂类"""
from typing import Dict
from app.services.exchanges.base import BaseExchange
from app.services.exchanges.toobit import ToobitExchange
from app.utils.logger import logger


class ExchangeFactory:
    """交易所工厂，用于创建交易所实例"""
    
    _exchanges: Dict[str, BaseExchange] = {}
    
    @classmethod
    def create(cls, exchange_name: str) -> BaseExchange:
        """
        创建交易所实例（单例模式）
        
        Args:
            exchange_name: 交易所名称，如toobit, binance, okx等
            
        Returns:
            交易所实例
            
        Raises:
            ValueError: 不支持的交易所
        """
        exchange_name = exchange_name.lower()
        
        # 如果已存在实例，直接返回
        if exchange_name in cls._exchanges:
            return cls._exchanges[exchange_name]
        
        # 创建新实例
        if exchange_name == "toobit":
            exchange = ToobitExchange()
        # 后续扩展：币安、OKX等
        # elif exchange_name == "binance":
        #     exchange = BinanceExchange()
        # elif exchange_name == "okx":
        #     exchange = OKXExchange()
        else:
            raise ValueError(f"不支持的交易所: {exchange_name}")
        
        # 缓存实例
        cls._exchanges[exchange_name] = exchange
        logger.info(f"创建交易所实例: {exchange_name}")
        
        return exchange
    
    @classmethod
    def get_supported_exchanges(cls) -> list:
        """
        获取支持的交易所列表
        
        Returns:
            支持的交易所名称列表
        """
        return ["toobit"]  # 后续扩展时更新此列表
