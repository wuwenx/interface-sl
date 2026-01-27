"""币安合约交易所实现（U 本位 / 币本位 - exchangeInfo）"""
from typing import List, Any, Optional
from app.services.exchanges.base import BaseExchange
from app.models.market import SymbolInfo, OrderBook
from app.utils.http_client import HttpClient
from app.config import get_exchange_config
from app.utils.logger import logger


def _parse_futures_filters(filters: list) -> dict:
    """解析币安合约 filters（PRICE_FILTER、LOT_SIZE）"""
    price_filter = next(
        (f for f in filters if f.get("filterType") == "PRICE_FILTER"),
        {},
    )
    lot_size_filter = next(
        (f for f in filters if f.get("filterType") == "LOT_SIZE"),
        {},
    )

    def _float(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    return {
        "min_price": _float(price_filter.get("minPrice")),
        "max_price": _float(price_filter.get("maxPrice")),
        "tick_size": _float(price_filter.get("tickSize")),
        "min_qty": _float(lot_size_filter.get("minQty")),
        "max_qty": _float(lot_size_filter.get("maxQty")),
        "step_size": _float(lot_size_filter.get("stepSize")),
    }


def _symbol_to_contract_info(s: dict) -> SymbolInfo:
    """将币安合约 symbol 结构转为 SymbolInfo（type=contract）"""
    filters = s.get("filters") or []
    fd = _parse_futures_filters(filters)

    # 合约使用 contractStatus 或 status，TRADING 为可交易
    status = s.get("contractStatus") or s.get("status") or ""

    def _precision(v: Any) -> Optional[str]:
        if v is None:
            return None
        return str(v) if v != "" else None

    base_precision = _precision(s.get("baseAssetPrecision") or s.get("pricePrecision"))
    quote_precision = _precision(s.get("quotePrecision") or s.get("quantityPrecision"))

    return SymbolInfo(
        symbol=s.get("symbol", ""),
        base_asset=s.get("baseAsset", ""),
        quote_asset=s.get("quoteAsset", ""),
        status=status,
        type="contract",
        base_asset_precision=base_precision,
        quote_precision=quote_precision,
        **fd,
    )


class BinanceUsdmExchange(BaseExchange):
    """
    币安 U 本位合约
    接口: GET /fapi/v1/exchangeInfo
    文档: https://binance-docs.github.io/apidocs/futures/en/#exchange-information
    """

    def __init__(self):
        super().__init__("binance_usdm")
        config = get_exchange_config("binance_usdm")
        self.client = HttpClient(
            base_url=config["base_url"],
            timeout=config["timeout"],
            retry_count=config["retry_count"],
        )
        self._path = "/fapi/v1/exchangeInfo"

    async def get_symbols(self) -> List[SymbolInfo]:
        try:
            resp = await self.client.get(self._path)
            symbols_raw = resp.get("symbols") or []
            result: List[SymbolInfo] = []
            for s in symbols_raw:
                st = (s.get("contractStatus") or s.get("status") or "").upper()
                if st != "TRADING":
                    continue
                result.append(_symbol_to_contract_info(s))
            logger.info(f"成功获取币安 U 本位合约交易对，共 {len(result)} 个")
            return result
        except Exception as e:
            logger.error(f"获取币安 U 本位合约交易对失败: {e}")
            raise

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> List:
        raise NotImplementedError("K线接口暂未实现")

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        raise NotImplementedError("深度接口暂未实现")

    async def close(self) -> None:
        await self.client.close()


class BinanceCoinmExchange(BaseExchange):
    """
    币安 币本位合约
    接口: GET /dapi/v1/exchangeInfo
    文档: https://binance-docs.github.io/apidocs/delivery/en/#exchange-information
    """

    def __init__(self):
        super().__init__("binance_coinm")
        config = get_exchange_config("binance_coinm")
        self.client = HttpClient(
            base_url=config["base_url"],
            timeout=config["timeout"],
            retry_count=config["retry_count"],
        )
        self._path = "/dapi/v1/exchangeInfo"

    async def get_symbols(self) -> List[SymbolInfo]:
        try:
            resp = await self.client.get(self._path)
            symbols_raw = resp.get("symbols") or []
            result: List[SymbolInfo] = []
            for s in symbols_raw:
                st = (s.get("contractStatus") or s.get("status") or "").upper()
                if st != "TRADING":
                    continue
                result.append(_symbol_to_contract_info(s))
            logger.info(f"成功获取币安 币本位合约交易对，共 {len(result)} 个")
            return result
        except Exception as e:
            logger.error(f"获取币安 币本位合约交易对失败: {e}")
            raise

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> List:
        raise NotImplementedError("K线接口暂未实现")

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        raise NotImplementedError("深度接口暂未实现")

    async def close(self) -> None:
        await self.client.close()
