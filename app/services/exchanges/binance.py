"""币安交易所实现（现货 API - 交易规范信息）"""
from typing import List, Any, Optional
from app.services.exchanges.base import BaseExchange
from app.models.market import SymbolInfo, OrderBook
from app.utils.http_client import HttpClient
from app.config import get_exchange_config
from app.utils.logger import logger


class BinanceExchange(BaseExchange):
    """
    币安交易所实现（现货）
    使用「交易规范信息」接口: GET /api/v3/exchangeInfo
    文档: https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/rest-api/general-endpoints
    """

    def __init__(self):
        """初始化币安交易所"""
        super().__init__("binance")
        config = get_exchange_config("binance")
        self.client = HttpClient(
            base_url=config["base_url"],
            timeout=config["timeout"],
            retry_count=config["retry_count"],
        )

    def _parse_filters(self, filters: list) -> dict:
        """解析 filters，得到价格/数量限制（PRICE_FILTER、LOT_SIZE）"""
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

    def _symbol_to_info(self, s: dict) -> SymbolInfo:
        """将币安现货 symbol 结构转为 SymbolInfo"""
        filters = s.get("filters") or []
        fd = self._parse_filters(filters)

        # 现货使用 status，如 TRADING
        status = s.get("status") or ""

        # 精度：文档中为数字，如 baseAssetPrecision: 8, quotePrecision: 8, quoteAssetPrecision: 8
        def _precision(v: Any) -> Optional[str]:
            if v is None:
                return None
            return str(v) if v != "" else None

        base_precision = _precision(s.get("baseAssetPrecision"))
        quote_precision = _precision(s.get("quotePrecision") or s.get("quoteAssetPrecision"))

        return SymbolInfo(
            symbol=s.get("symbol", ""),
            base_asset=s.get("baseAsset", ""),
            quote_asset=s.get("quoteAsset", ""),
            status=status,
            type="spot",  # 现货接口，均为 spot
            base_asset_precision=base_precision,
            quote_precision=quote_precision,
            **fd,
        )

    async def get_symbols(self) -> List[SymbolInfo]:
        """获取交易规范信息（币安现货）。"""
        try:
            # 币安现货「交易规范信息」: GET /api/v3/exchangeInfo
            resp = await self.client.get("/api/v3/exchangeInfo")
            symbols_raw = resp.get("symbols") or []
            result: List[SymbolInfo] = []
            for s in symbols_raw:
                if (s.get("status") or "").upper() != "TRADING":
                    continue
                result.append(self._symbol_to_info(s))
            logger.info(f"成功获取币安现货交易对，共 {len(result)} 个")
            return result
        except Exception as e:
            logger.error(f"获取币安交易对失败: {e}")
            raise

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
    ) -> List:
        """K线暂未实现"""
        raise NotImplementedError("K线接口暂未实现")

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """深度暂未实现"""
        raise NotImplementedError("深度接口暂未实现")

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        await self.client.close()
