"""交易所基类"""
from abc import ABC, abstractmethod
from typing import List
from app.models.market import SymbolInfo, KlineData, OrderBook


class BaseExchange(ABC):
    """交易所基类，定义统一接口"""
    
    def __init__(self, name: str):
        """
        初始化交易所
        
        Args:
            name: 交易所名称
        """
        self.name = name
    
    @abstractmethod
    async def get_symbols(self) -> List[SymbolInfo]:
        """
        获取所有币对信息
        
        Returns:
            币对信息列表
        """
        pass
    
    @abstractmethod
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
    ) -> List[KlineData]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对符号，如BTC_USDT
            interval: K线周期，如1m, 5m, 1h, 1d等
            limit: 返回数据条数，默认100
            
        Returns:
            K线数据列表
        """
        pass
    
    @abstractmethod
    async def get_orderbook(
        self,
        symbol: str,
        limit: int = 20,
    ) -> OrderBook:
        """
        获取深度数据（订单簿）
        
        Args:
            symbol: 交易对符号，如BTC_USDT
            limit: 返回深度条数，默认20
            
        Returns:
            订单簿数据
        """
        pass
    
    def normalize_symbol(self, symbol: str) -> str:
        """
        标准化交易对符号（子类可重写）
        
        Args:
            symbol: 原始交易对符号
            
        Returns:
            标准化后的交易对符号
        """
        return symbol.upper()
    
    def normalize_interval(self, interval: str) -> str:
        """
        标准化K线周期（子类可重写）
        
        Args:
            interval: 原始K线周期
            
        Returns:
            标准化后的K线周期
        """
        return interval.lower()
