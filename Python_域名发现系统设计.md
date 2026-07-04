# Python 域名发现系统设计（免费方案）

## 目标

每天自动发现**已经删除且可重新注册**的高价值 `.com`
域名，尽量使用免费数据源，并减少 API 查询成本。

## 整体架构

``` text
scheduler.py
      │
      ▼
download_zone.py
      │
      ▼
diff_zone.py
      │
      ▼
filter_domains.py
      │
      ▼
brand_score.py
      │
      ▼
availability.py
      │
      ▼
history_check.py
      │
      ▼
notify.py
```

每天由 cron 或 APScheduler 定时执行。

## 项目目录

``` text
domain_hunter/
├── app.py
├── config.py
├── requirements.txt
├── downloader/
├── diff/
├── filters/
├── scorer/
├── checker/
├── notifier/
├── database/
├── data/
└── cache/
```

## 数据来源

1.  ICANN CZDS（每天下载 `.com` Zone）
2.  本地计算 Zone 差分
3.  Availability API（仅查询高价值候选）
4.  Wayback（仅对可注册域名检查历史）

## 数据流程

``` text
CZDS
  │
下载 Zone
  │
昨天 Zone vs 今天 Zone
  │
求差集
  │
规则过滤
  │
品牌评分
  │
Top 100~1000
  │
Availability 查询
  │
Available?
  │
Wayback 检查
  │
Telegram/邮件通知
```

## SQLite 数据表

### domains

-   id
-   domain
-   tld
-   length
-   deleted_date
-   status

### score

-   domain_id
-   brand_score
-   dictionary_score
-   trend_score
-   total_score

### history

-   domain_id
-   archive
-   spam
-   notes

## Zone 差分

使用 Python `set`：

``` python
today = set()
yesterday = set()
deleted = yesterday - today
```

## 过滤规则

-   长度 4\~12
-   仅字母
-   无数字
-   无连字符
-   `.com`
-   至少一个元音
-   不连续四个辅音

采用插件化 Filter：

``` python
class Filter:
    def match(self, domain):
        ...
```

## 品牌评分

建议规则：

-   长度 ≤ 8：+20
-   纯字母：+20
-   AI 关键词：+15
-   字典词：+30
-   易发音：+15
-   双词组合：+20
-   数字：-30
-   连字符：-50

## AI 评分（可选）

部署本地模型（Qwen、Gemma、Mistral），从品牌价值、SEO、国际化、商业价值等维度评分。

## Availability 查询

使用 `asyncio + aiohttp/httpx` 并发查询，仅针对 Top 候选域名。

## Wayback 检查

仅检查可注册域名是否存在垃圾站、色情站或菠菜历史。

## 通知

推荐 Telegram Bot，也可扩展邮件、企业微信、Discord。

## requirements.txt

-   aiohttp
-   httpx
-   aiosqlite
-   rapidfuzz
-   wordfreq
-   nltk
-   tldextract
-   apscheduler
-   orjson
-   beautifulsoup4
-   lxml
-   python-dotenv
-   openai
-   rich
-   typer

## 后续扩展

-   商标检测
-   AI 趋势词加权
-   域名历史成交价格
-   FastAPI 管理后台
-   PostgreSQL 替换 SQLite
-   Redis 缓存
