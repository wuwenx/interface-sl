"""HTTP客户端封装"""
import asyncio
from typing import Dict, Any, Optional
import httpx
from app.utils.logger import logger


class HttpClient:
    """异步HTTP客户端"""
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 10,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        初始化HTTP客户端
        
        Args:
            base_url: API基础URL
            timeout: 请求超时时间（秒）
            retry_count: 重试次数
            retry_delay: 重试延迟（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            follow_redirects=True,
        )
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        发送GET请求
        
        Args:
            endpoint: API端点
            params: 查询参数
            headers: 请求头
            
        Returns:
            JSON响应数据
            
        Raises:
            httpx.HTTPError: HTTP请求错误
        """
        url = f"{self.base_url}{endpoint}"
        last_exception = None
        
        for attempt in range(self.retry_count):
            try:
                logger.debug(f"GET请求: {url}, 参数: {params}, 尝试次数: {attempt + 1}")
                response = await self.client.get(
                    endpoint,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
            
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP状态错误: {e.response.status_code}, 响应: {e.response.text}")
                last_exception = e
                if e.response.status_code < 500:  # 4xx错误不重试
                    raise
            
            except httpx.RequestError as e:
                logger.warning(f"请求错误: {e}, 尝试次数: {attempt + 1}/{self.retry_count}")
                last_exception = e
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        # 所有重试都失败
        raise last_exception
    
    async def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        发送POST请求
        
        Args:
            endpoint: API端点
            data: 表单数据
            json: JSON数据
            headers: 请求头
            
        Returns:
            JSON响应数据
            
        Raises:
            httpx.HTTPError: HTTP请求错误
        """
        url = f"{self.base_url}{endpoint}"
        last_exception = None
        
        for attempt in range(self.retry_count):
            try:
                logger.debug(f"POST请求: {url}, 尝试次数: {attempt + 1}")
                response = await self.client.post(
                    endpoint,
                    data=data,
                    json=json,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
            
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP状态错误: {e.response.status_code}, 响应: {e.response.text}")
                last_exception = e
                if e.response.status_code < 500:  # 4xx错误不重试
                    raise
            
            except httpx.RequestError as e:
                logger.warning(f"请求错误: {e}, 尝试次数: {attempt + 1}/{self.retry_count}")
                last_exception = e
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        # 所有重试都失败
        raise last_exception
