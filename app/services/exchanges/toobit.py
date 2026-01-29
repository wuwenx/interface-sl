"""Toobit交易所实现"""
from typing import List
from app.services.exchanges.base import BaseExchange
from app.models.market import SymbolInfo
from app.utils.http_client import HttpClient
from app.config import get_exchange_config
from app.utils.logger import logger


class ToobitExchange(BaseExchange):
    """Toobit交易所实现"""
    
    def __init__(self):
        """初始化Toobit交易所"""
        super().__init__("toobit")
        config = get_exchange_config("toobit")
        self.client = HttpClient(
            base_url=config["base_url"],
            timeout=config["timeout"],
            retry_count=config["retry_count"],
        )
    
    def _parse_filters(self, filters: list) -> dict:
        """
        解析过滤器信息
        
        Args:
            filters: 过滤器列表
            
        Returns:
            包含价格和数量限制的字典
        """
        price_filter = next(
            (f for f in filters if f.get("filterType") == "PRICE_FILTER"),
            {}
        )
        lot_size_filter = next(
            (f for f in filters if f.get("filterType") == "LOT_SIZE"),
            {}
        )
        
        # 处理价格过滤器
        min_price = None
        max_price = None
        tick_size = None
        if price_filter:
            min_price_str = price_filter.get("minPrice")
            max_price_str = price_filter.get("maxPrice")
            tick_size_str = price_filter.get("tickSize")
            if min_price_str:
                try:
                    min_price = float(min_price_str)
                except (ValueError, TypeError):
                    pass
            if max_price_str:
                try:
                    max_price = float(max_price_str)
                except (ValueError, TypeError):
                    pass
            if tick_size_str:
                try:
                    tick_size = float(tick_size_str)
                except (ValueError, TypeError):
                    pass
        
        # 处理数量过滤器
        min_qty = None
        max_qty = None
        step_size = None
        if lot_size_filter:
            min_qty_str = lot_size_filter.get("minQty")
            max_qty_str = lot_size_filter.get("maxQty")
            step_size_str = lot_size_filter.get("stepSize")
            if min_qty_str:
                try:
                    min_qty = float(min_qty_str)
                except (ValueError, TypeError):
                    pass
            if max_qty_str:
                try:
                    max_qty = float(max_qty_str)
                except (ValueError, TypeError):
                    pass
            if step_size_str:
                try:
                    step_size = float(step_size_str)
                except (ValueError, TypeError):
                    pass
        
        return {
            "min_price": min_price,
            "max_price": max_price,
            "tick_size": tick_size,
            "min_qty": min_qty,
            "max_qty": max_qty,
            "step_size": step_size,
        }
    
    def _parse_symbol_data(self, symbol_data: dict, symbol_type: str) -> SymbolInfo:
        """
        解析单个交易对数据
        
        Args:
            symbol_data: 交易对原始数据
            symbol_type: 交易对类型，"spot" 或 "contract"
            
        Returns:
            SymbolInfo对象
        """
        filters = symbol_data.get("filters", [])
        filter_data = self._parse_filters(filters)
        
        # 解析精度字段（现货用quotePrecision，合约用quoteAssetPrecision）
        base_asset_precision = symbol_data.get("baseAssetPrecision")
        quote_precision = symbol_data.get("quotePrecision") or symbol_data.get("quoteAssetPrecision")
        
        return SymbolInfo(
            symbol=symbol_data.get("symbol", ""),
            base_asset=symbol_data.get("baseAsset", ""),
            quote_asset=symbol_data.get("quoteAsset", ""),
            status=symbol_data.get("status", ""),
            type=symbol_type,
            base_asset_precision=base_asset_precision,
            quote_precision=quote_precision,
            **filter_data
        )
    
    async def get_symbols(self) -> List[SymbolInfo]:
        """
        获取所有币对信息（包括现货和合约）
        
        Returns:
            币对信息列表
        """
        symbols, _ = await self.get_symbols_with_raw_data()
        return symbols
    
    async def get_symbols_with_raw_data(self) -> tuple[List[SymbolInfo], dict]:
        """
        获取所有币对信息（包括现货和合约），同时返回原始API响应
        
        Returns:
            (币对信息列表, 原始API响应数据)
        """
        try:
            # 调用Toobit API获取交易规则和交易对
            response = await self.client.get("/api/v1/exchangeInfo")
            
            symbol_list = []
            
            # 处理现货交易对（symbols）
            symbols_data = response.get("symbols", [])
            for symbol_data in symbols_data:
                # 只处理状态为TRADING的交易对
                if symbol_data.get("status") != "TRADING":
                    continue
                
                symbol_info = self._parse_symbol_data(symbol_data, "spot")
                symbol_list.append(symbol_info)
            
            # 处理合约交易对（contracts）
            contracts_data = response.get("contracts", [])
            for contract_data in contracts_data:
                # 只处理状态为TRADING的合约
                if contract_data.get("status") != "TRADING":
                    continue
                # 过滤掉 TBV_ 或 TBV- 开头的合约（如 TBV-ETH-SWAP-TBV-USDT）
                symbol_raw = contract_data.get("symbol", "")
                if symbol_raw.startswith("TBV_") or symbol_raw.startswith("TBV-"):
                    continue

                symbol_info = self._parse_symbol_data(contract_data, "contract")
                symbol_list.append(symbol_info)
            
            logger.info(f"成功获取Toobit币对信息，共{len(symbol_list)}个交易对（现货+合约）")
            return symbol_list, response
        
        except Exception as e:
            logger.error(f"获取Toobit币对信息失败: {e}")
            raise
    
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
    ) -> List:
        """
        获取K线数据（暂未实现）
        
        Args:
            symbol: 交易对符号
            interval: K线周期
            limit: 返回数据条数
            
        Returns:
            K线数据列表
        """
        raise NotImplementedError("K线接口暂未实现")
    
    async def get_orderbook(
        self,
        symbol: str,
        limit: int = 20,
    ):
        """
        获取深度数据（暂未实现）
        
        Args:
            symbol: 交易对符号
            limit: 返回深度条数
            
        Returns:
            订单簿数据
        """
        raise NotImplementedError("深度接口暂未实现")
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.client.close()
