"""市场数据模型"""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class SymbolInfo(BaseModel):
    """币对信息"""
    symbol: str = Field(..., description="交易对符号，如BTCUSDT")
    base_asset: str = Field(..., description="基础资产，如BTC")
    quote_asset: str = Field(..., description="计价资产，如USDT")
    status: str = Field(..., description="交易状态，如TRADING")
    type: str = Field(default="spot", description="交易对类型：spot(现货) 或 contract(合约)")
    base_asset_precision: Optional[str] = Field(None, description="基础资产精度，如0.0001")
    quote_precision: Optional[str] = Field(None, description="计价资产精度，如0.01")
    min_price: Optional[float] = Field(None, description="最小价格")
    max_price: Optional[float] = Field(None, description="最大价格")
    tick_size: Optional[float] = Field(None, description="价格精度")
    min_qty: Optional[float] = Field(None, description="最小数量")
    max_qty: Optional[float] = Field(None, description="最大数量")
    step_size: Optional[float] = Field(None, description="数量精度")
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
                "status": "TRADING",
                "type": "spot",
                "base_asset_precision": "0.0001",
                "quote_precision": "0.01",
                "min_price": 0.01,
                "max_price": 1000000.0,
                "tick_size": 0.01,
                "min_qty": 0.00001,
                "max_qty": 1000.0,
                "step_size": 0.00001,
            }
        }


class KlineData(BaseModel):
    """K线数据"""
    timestamp: int = Field(..., description="时间戳（毫秒）")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: float = Field(..., description="成交量")
    quote_volume: Optional[float] = Field(None, description="成交额")
    trades: Optional[int] = Field(None, description="成交笔数")
    
    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": 1609459200000,
                "open": 29000.0,
                "high": 29500.0,
                "low": 28800.0,
                "close": 29300.0,
                "volume": 100.5,
                "quote_volume": 2930000.0,
                "trades": 1250,
            }
        }


class OrderBookEntry(BaseModel):
    """订单簿条目"""
    price: float = Field(..., description="价格")
    quantity: float = Field(..., description="数量")
    
    class Config:
        json_schema_extra = {
            "example": {
                "price": 29000.0,
                "quantity": 1.5,
            }
        }


class OrderBook(BaseModel):
    """深度数据（订单簿）"""
    symbol: str = Field(..., description="交易对符号")
    bids: List[OrderBookEntry] = Field(..., description="买单列表，按价格从高到低排序")
    asks: List[OrderBookEntry] = Field(..., description="卖单列表，按价格从低到高排序")
    timestamp: Optional[int] = Field(None, description="时间戳（毫秒）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTC_USDT",
                "bids": [
                    {"price": 29000.0, "quantity": 1.5},
                    {"price": 28999.0, "quantity": 2.0},
                ],
                "asks": [
                    {"price": 29001.0, "quantity": 1.2},
                    {"price": 29002.0, "quantity": 3.0},
                ],
                "timestamp": 1609459200000,
            }
        }
