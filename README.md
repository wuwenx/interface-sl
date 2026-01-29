# 多交易所API后端接口项目

一个基于Python FastAPI的多交易所统一API接口服务，提供币对信息、K线、深度等市场数据的统一访问接口。

## 功能特性

- ✅ 支持多交易所（当前支持Toobit，可扩展币安、OKX等）
- ✅ 统一的RESTful API接口
- ✅ 自动API文档生成（Swagger UI）
- ✅ 异步HTTP请求，高性能
- ✅ 完善的错误处理和日志记录
- ✅ 支持CORS跨域访问
- ✅ **MySQL数据库缓存，防止API限频**

## 技术栈

- **后端框架**: FastAPI 0.104.1
- **HTTP客户端**: httpx 0.25.2（异步）
- **数据验证**: Pydantic 2.5.0
- **配置管理**: python-dotenv 1.0.0
- **日志**: loguru 0.7.2
- **数据库**: MySQL + SQLAlchemy 2.0.23 + aiomysql 0.2.0

## 项目结构

```
interface-sl/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI应用入口
│   ├── config.py               # 配置管理
│   ├── database.py             # 数据库连接和会话管理
│   ├── models/                 # 数据模型
│   │   ├── __init__.py
│   │   ├── common.py           # 通用响应模型
│   │   ├── market.py           # 市场数据模型
│   │   └── db_models.py        # 数据库模型
│   ├── services/               # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── exchange_factory.py # 交易所工厂类
│   │   ├── cache_service.py    # 缓存服务
│   │   └── exchanges/          # 各交易所实现
│   │       ├── __init__.py
│   │       ├── base.py         # 交易所基类
│   │       └── toobit.py       # Toobit实现
│   ├── routers/                # API路由
│   │   ├── __init__.py
│   │   └── market.py           # 市场数据接口
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── http_client.py      # HTTP客户端封装
│       └── logger.py           # 日志配置
├── tests/                      # 测试文件
├── init_database.sql           # 数据库初始化SQL脚本
├── .env.example                # 环境变量示例
├── .gitignore
├── requirements.txt            # Python依赖
└── README.md                   # 项目说明文档
```

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

### 2. 配置MySQL数据库

#### 2.1 创建数据库

```bash
# 使用MySQL客户端执行SQL脚本
mysql -u root -p < init_database.sql

# 或者手动创建
mysql -u root -p
CREATE DATABASE exchange_api DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

#### 2.2 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置数据库连接信息：

```env
# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=exchange_api
DB_CHARSET=utf8mb4

# 缓存配置
CACHE_TTL=3600  # 缓存过期时间（秒），默认1小时
```

### 3. 启动服务

```bash
source venv/bin/activate
# 使用uvicorn启动
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 或使用Python直接运行
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. 访问API文档

启动后访问以下地址查看API文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API接口说明

### 1. 获取币对列表（带缓存）

**接口地址**: `GET /api/v1/symbols`

**请求参数**:
- `exchange` (可选): 交易所名称，默认 `toobit`
- `type` (可选): 交易对类型，`spot`(现货) 或 `contract`(合约)，不传则返回全部

**缓存机制**:
- 首次请求会从API获取数据并保存到数据库
- 后续请求在缓存有效期内（默认1小时）直接从数据库读取
- 缓存过期后自动从API更新

**响应示例**:
```json
{
  "code": 200,
  "message": "获取币对列表成功",
  "data": [
    {
      "symbol": "BTCUSDT",
      "base_asset": "BTC",
      "quote_asset": "USDT",
      "status": "TRADING",
      "type": "spot",
      "min_price": 0.01,
      "max_price": 100000.0,
      "tick_size": 0.01,
      "min_qty": 0.0001,
      "max_qty": 4000.0,
      "step_size": 0.0001
    }
  ]
}
```

**使用示例**:
```bash
# 获取所有交易对（现货+合约）
curl http://localhost:8000/api/v1/symbols

# 只获取现货交易对
curl http://localhost:8000/api/v1/symbols?type=spot

# 只获取合约交易对
curl http://localhost:8000/api/v1/symbols?type=contract

# 指定交易所
curl http://localhost:8000/api/v1/symbols?exchange=toobit&type=spot
```

### 2. 获取K线数据（暂未实现）

**接口地址**: `GET /api/v1/klines`

**状态**: 501 Not Implemented

### 3. 获取深度数据（暂未实现）

**接口地址**: `GET /api/v1/depth`

**状态**: 501 Not Implemented

## 数据模型

### SymbolInfo（币对信息）

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | string | 交易对符号，如BTCUSDT |
| base_asset | string | 基础资产，如BTC |
| quote_asset | string | 计价资产，如USDT |
| status | string | 交易状态，如TRADING |
| type | string | 交易对类型：spot(现货) 或 contract(合约) |
| min_price | float | 最小价格（可选） |
| max_price | float | 最大价格（可选） |
| tick_size | float | 价格精度（可选） |
| min_qty | float | 最小数量（可选） |
| max_qty | float | 最大数量（可选） |
| step_size | float | 数量精度（可选） |

## 缓存机制

### 工作原理

1. **首次请求**: 从交易所API获取数据 → 保存到MySQL数据库 → 返回给前端
2. **后续请求**: 检查数据库缓存是否有效（未过期）→ 如果有效，直接从数据库读取 → 返回给前端
3. **缓存过期**: 缓存过期后，重新从API获取 → 更新数据库 → 返回给前端

### 缓存配置

在 `.env` 文件中配置：

```env
# 缓存过期时间（秒），默认3600秒（1小时）
CACHE_TTL=3600
```

### 数据库表结构

`exchange_symbols` 表存储所有交易所的币对信息，包含以下字段：
- 交易所名称、交易对符号、类型（现货/合约）
- 价格和数量限制信息
- 原始API响应数据（JSON格式）
- 创建时间和更新时间（用于判断缓存是否过期）

## 配置说明

环境变量配置项（`.env`文件）：

```env
# 应用配置
APP_NAME=Exchange API
APP_VERSION=1.0.0
DEBUG=False

# 服务器配置
HOST=0.0.0.0
PORT=8000

# Toobit API配置
TOOBIT_BASE_URL=https://api.toobit.com
TOOBIT_TIMEOUT=10
TOOBIT_RETRY_COUNT=3

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=exchange_api
DB_CHARSET=utf8mb4

# 缓存配置
CACHE_TTL=3600
```

## 开发说明

### 添加新交易所支持

1. 在 `app/services/exchanges/` 目录下创建新的交易所实现类，继承 `BaseExchange`
2. 实现所有抽象方法：`get_symbols()`, `get_klines()`, `get_orderbook()`
3. 在 `app/services/exchange_factory.py` 中注册新交易所
4. 在 `app/config.py` 中添加新交易所的配置项

### 扩展WebSocket支持

后续版本将支持WebSocket实时数据推送，可在 `BaseExchange` 中添加WebSocket相关抽象方法。

## 错误处理

所有API接口使用统一的错误响应格式：

```json
{
  "code": 400,
  "message": "错误描述",
  "data": null
}
```

常见错误码：
- `200`: 成功
- `400`: 请求参数错误
- `500`: 服务器内部错误
- `501`: 功能未实现

## 日志

日志文件默认保存在 `logs/app.log`，支持自动轮转和压缩。

日志级别可通过 `LOG_LEVEL` 环境变量配置。

## 许可证

MIT License

## 后续计划

- [x] 实现币对信息接口（带MySQL缓存）
- [ ] 实现K线数据接口
- [ ] 实现深度数据接口
- [ ] 添加币安（Binance）交易所支持
- [ ] 添加OKX交易所支持
- [ ] 实现WebSocket实时数据推送
- [ ] 添加Redis缓存（可选，提升性能）
- [ ] 添加认证和限流中间件
