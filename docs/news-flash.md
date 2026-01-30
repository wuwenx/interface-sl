# 新闻快讯逻辑说明

本文档说明新闻快讯功能的整体逻辑、何时请求外部 API、何时只读数据库，以及接口与配置说明。

---

## 1. 核心结论

| 操作 | 是否请求外部 API | 说明 |
|------|------------------|------|
| **GET /api/v1/news** | ❌ 否 | 只从数据库分页查询，不请求外部 |
| **GET /api/v1/news/{id}** | ❌ 否 | 只从数据库按 id 查详情，不请求外部 |
| **POST /api/v1/news/refresh** | ✅ 是 | 从配置的数据源（CryptoCompare、RSS 等）拉取并写入库 |
| **应用启动** | ✅ 一次 | 后台任务执行一次拉取 + 入库，便于首屏有数据 |

**结论：请求 `/news` 列表或详情不会请求外部 API，只有“刷新”或启动时才会拉取外部数据。**

---

## 2. 数据流概览

```
┌─────────────────────────────────────────────────────────────────┐
│  外部数据源（CryptoCompare API、CoinDesk RSS 等）                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ 仅在下述时机请求：
                             │ • POST /api/v1/news/refresh
                             │ • 应用启动时后台任务
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  fetch_all_sources_and_save()                                    │
│  拉取 → 翻译（可选）→ 按 url 去重写入/更新 news_articles           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  数据库表 news_articles                                           │
│  （title, summary, content, title_zh, summary_zh, content_zh…）  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ GET /news、GET /news/{id} 只读库
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  前端 / 客户端                                                    │
│  GET /api/v1/news?page=1&lang=zh  → 分页列表（可中英文）          │
│  GET /api/v1/news/{id}?lang=zh    → 详情（可中英文）              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 接口行为说明

### 3.1 GET /api/v1/news（列表）

- **作用**：分页返回新闻列表，供前端展示或下拉加载。
- **数据来源**：仅查数据库表 `news_articles`，按 `published_at`、`created_at` 倒序分页。
- **是否请求外部 API**：**否**。
- **参数**：
  - `page`：页码，默认 1
  - `page_size`：每页条数，默认 20
  - `lang`：`en`（默认）或 `zh`，控制返回标题/摘要的语言（有中文则返回中文，否则退回英文）

### 3.2 GET /api/v1/news/{article_id}（详情）

- **作用**：返回单条新闻详情（含正文）。
- **数据来源**：仅按 `id` 从数据库查询。
- **是否请求外部 API**：**否**。
- **参数**：`lang` 同上，控制标题/摘要/正文的语言。

### 3.3 POST /api/v1/news/refresh（刷新）

- **注意**：必须使用 **POST** 方法。若误用 GET 会返回 405，并提示使用 POST。
- **作用**：从配置的新闻数据源拉取最新内容，翻译后写入或更新数据库。
- **数据来源**：**会请求外部**（如 CryptoCompare API、CoinDesk RSS 等，见配置）。
- **流程**：`fetch_all_sources_and_save(db)` → 拉取各源 → 翻译标题/摘要/正文 → 按 `url` 去重，存在则更新、不存在则插入。
- **使用场景**：前端“下拉刷新”时先调此接口，再调 GET /news 拿到最新列表。

### 3.4 POST /api/v1/news/translate（翻译回填）

- **注意**：必须使用 **POST** 方法。若误用 GET 会返回 405，并提示使用 POST。
- **作用**：对库中尚未有中文的新闻（`title_zh` 为空）做翻译回填。
- **数据来源**：不请求新闻外部 API，仅读库 + 调用翻译服务（如 Google 翻译）写回 `title_zh`、`summary_zh`、`content_zh`。
- **参数**：`limit`：最多处理条数，默认 50，最大 200。

---

## 4. 应用启动时的行为

- 在 `app/main.py` 的 `startup_event` 中，会创建一个**后台任务**：
  - 调用一次 `fetch_all_sources_and_save(session)`，即拉取配置的所有数据源并写入/更新 `news_articles`。
- 因此**首次部署或重启后**，无需手动调 refresh，首屏请求 GET /news 就能读到数据（来自这次启动时的拉取）。
- 之后若需要更新，由前端在适当时机调用 **POST /api/v1/news/refresh**。

---

## 5. 数据源配置

- 数据源在配置中维护（如 `app/config.py` 的 `get_news_sources()`），可通过环境变量 `NEWS_SOURCES`（JSON 数组）覆盖默认。
- 默认包含两个源：
  - **CryptoCompare**（API）
  - **CoinDesk**（RSS）
- 每项需包含：`type`（`api` / `rss`）、`name`、`url`，API 类可加 `response_path` 等。详见 `.env.example` 或配置注释。

---

## 6. 中文与语言参数

- 拉取并保存时会对标题/摘要/正文做一次翻译，写入 `title_zh`、`summary_zh`、`content_zh`。
- 列表和详情接口通过 **`lang`** 控制返回语言：
  - `lang=zh`（或 `zh-cn`、`zh_cn`）：优先返回 `*_zh` 字段，若无则退回英文。
  - 默认或不传 `lang`：返回英文字段。
- 若库里已有旧数据没有中文，可调用 **POST /api/v1/news/translate** 做翻译回填，再使用 GET /news?lang=zh 查看中文。

---

## 7. 相关代码位置

| 逻辑 | 文件 |
|------|------|
| 列表/详情/refresh/translate 路由 | `app/routers/news.py` |
| 拉取、翻译、入库、列表查询 | `app/services/news_service.py` |
| 新闻表模型 | `app/models/db_models.py`（`NewsArticle`） |
| 启动时拉取一次 | `app/main.py`（`startup_event` 中 `_first_news_fetch`） |
| 数据源配置 | `app/config.py`（`get_news_sources`、`news_sources`） |

---

以上即为新闻快讯的完整逻辑说明；**请求 GET /news 不会请求外部 API，只有刷新或启动时才会拉取并更新数据库。**
