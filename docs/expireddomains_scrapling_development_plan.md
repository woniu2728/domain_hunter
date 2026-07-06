# ExpiredDomains.net + Scrapling 开发方案

## 目标

当前系统不再依赖 Zone 文件获取已删除域名，改为使用 Scrapling 抓取 ExpiredDomains.net 每日更新的已删除且页面标记为可注册的域名。

本次重构不保留 Zone 兼容逻辑。后续代码、配置页、调度器和数据库模型都以 ExpiredDomains.net 数据源为主。

## 边界

允许做：

- 低频抓取。
- 单账号单任务低并发访问。
- 账号池健康状态管理。
- 账号绑定固定代理。
- 代理连通性测试和冷却。
- Session/Cookie 复用。
- 请求间隔、最大页数、失败退避。
- 页面快照保存，方便解析器维护。
- 发现验证码、403、429、登录失效时停止任务并提示人工处理。

不做：

- 验证码绕过。
- 高频并发抓取。
- 自动注册账号。
- 封禁后无限代理轮换。
- 批量代理池撞站。
- 绕过目标站明确限制的访问策略。

## 总体流程

```text
按 TLD 定时触发任务
  -> 清理该 TLD 过期源数据
  -> 选择健康账号
  -> 绑定账号代理或全局代理
  -> 登录或恢复 session
  -> 抓取 ExpiredDomains.net 对应 TLD 的每日删除列表
  -> 分页解析表格
  -> 只保留页面标记 available 的域名
  -> 落库 deleted_domain_sources
  -> 读取今日源数据
  -> 规则过滤
  -> AI/本地评分
  -> 二次可注册查询
  -> Wayback 检查
  -> 邮件通知
```

ExpiredDomains.net 的 available 只作为初筛。最终是否可注册仍以系统自己的可注册查询结果为准。

## 配置模型

新增配置字段，替代现有 `zone_sources`。

```json
{
  "source_type": "expireddomains",
  "expireddomains_accounts": [
    {
      "id": "acc-1",
      "username": "user1",
      "password": "pass1",
      "enabled": true,
      "proxy_id": "proxy-us-1",
      "status": "healthy",
      "last_error": "",
      "last_used_at": ""
    }
  ],
  "expireddomains_proxies": [
    {
      "id": "proxy-us-1",
      "name": "US 1",
      "url": "http://user:pass@1.2.3.4:8080",
      "enabled": true,
      "status": "healthy",
      "last_error": ""
    }
  ],
  "expireddomains_default_proxy_id": "",
  "expireddomains_tld_schedules": [
    {
      "tld": "com",
      "enabled": true,
      "crawl_hour": 3,
      "crawl_minute": 30,
      "timezone": "Asia/Shanghai",
      "max_pages": 20,
      "request_delay_seconds": 12
    }
  ],
  "expireddomains_cleanup_enabled": true,
  "expireddomains_keep_days": 1
}
```

密码、代理 URL 中的认证信息都按 secret 处理，前端返回时显示 `********`。

## 账号池

### 状态

```text
healthy       正常
cooldown      临时冷却
login_failed  登录失败或密码错误
limited       403/429/访问受限
captcha       需要人工处理验证码
disabled      手动禁用
```

### 选择规则

1. 只选择 `enabled = true` 的账号。
2. 优先选择 `healthy`。
3. 没有 healthy 时，选择冷却已过期的 `cooldown` 账号。
4. `login_failed`、`captcha`、`disabled` 不自动参与任务。
5. 每次任务记录 account_id。

### 失败处理

- 登录失败：账号标记 `login_failed`，任务换下一个账号。
- 403/429：账号标记 `limited` 或 `cooldown`，任务换下一个账号。
- 验证码：账号标记 `captcha`，当前 TLD 任务停止。
- 所有账号不可用：任务 failed，并记录 `没有可用账号`。

## 代理池

### 支持协议

先支持：

```text
http://host:port
http://user:pass@host:port
https://host:port
socks5://user:pass@host:port
```

SOCKS5 是否可用以 Scrapling 底层 fetcher/browser 支持为准。实现时如果普通 fetcher 不支持 SOCKS5，可以先在前端提示仅 browser 模式可用，或者第一阶段只支持 HTTP/HTTPS。

### 绑定策略

- 优先使用账号绑定代理。
- 账号未绑定代理时，使用全局默认代理。
- 账号使用的代理应保持稳定，不建议同一账号频繁换 IP。
- 一个账号可以配置一个主代理，后续可扩展备用代理列表。

### 状态

```text
healthy
cooldown
failed
disabled
```

### 测试代理

后端提供测试接口，请求 ExpiredDomains.net 轻量页面：

```text
POST /api/crawler/proxies/{id}/test
```

返回：

```json
{
  "status": "ok",
  "latency_ms": 850
}
```

失败时记录 last_error。

## TLD 调度

不同后缀删除时间不一致，所以每个 TLD 独立配置定时任务。

示例：

```text
expireddomains-com-daily -> 每天 03:30
expireddomains-net-daily -> 每天 04:15
expireddomains-org-daily -> 每天 05:00
```

调度器 reload 时：

1. 删除所有旧的 ExpiredDomains TLD job。
2. 遍历启用的 `expireddomains_tld_schedules`。
3. 为每个 TLD 注册独立 cron job。
4. job id 使用 `expireddomains-{tld}-daily`。

同一 TLD 同一时间只允许一个运行中任务。不同 TLD 是否并行第一阶段建议不并行，统一限制全局单并发，降低访问风险。

## 数据清理

用户要求第二天爬取时删除前一天数据。建议清理范围：

- 删除 `deleted_domain_sources` 中超过保留天数的数据。
- 不删除 `domains`、`score`、`history`、`jobs`、`crawler_runs`。

原因：

- 源数据是每日临时池，可以清理。
- 最终候选、评分、历史和任务记录用于排查与审计，不应被每日任务删除。

默认：

```text
expireddomains_keep_days = 1
```

即每天抓取前只保留当天源数据。

## 数据库设计

### crawler_accounts

```sql
CREATE TABLE IF NOT EXISTS crawler_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    proxy_id INTEGER,
    status TEXT NOT NULL DEFAULT 'healthy',
    cooldown_until TEXT,
    last_error TEXT,
    last_used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### crawler_proxies

```sql
CREATE TABLE IF NOT EXISTS crawler_proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'healthy',
    cooldown_until TEXT,
    last_error TEXT,
    last_used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### crawler_tld_schedules

```sql
CREATE TABLE IF NOT EXISTS crawler_tld_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    tld TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    crawl_hour INTEGER NOT NULL,
    crawl_minute INTEGER NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    max_pages INTEGER NOT NULL DEFAULT 20,
    request_delay_seconds INTEGER NOT NULL DEFAULT 12,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, tld)
);
```

### deleted_domain_sources

```sql
CREATE TABLE IF NOT EXISTS deleted_domain_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    tld TEXT NOT NULL,
    provider TEXT NOT NULL,
    source_status TEXT NOT NULL,
    dropped_date TEXT,
    source_date TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain, provider, source_date)
);
```

### crawler_runs

```sql
CREATE TABLE IF NOT EXISTS crawler_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    tld TEXT NOT NULL,
    account_id INTEGER,
    proxy_id INTEGER,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    pages_fetched INTEGER NOT NULL DEFAULT 0,
    domains_seen INTEGER NOT NULL DEFAULT 0,
    available_seen INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
```

## 后端模块

新增：

```text
crawler/
  __init__.py
  account_pool.py
  proxy_pool.py
  expireddomains.py
  expireddomains_parser.py
  types.py

backend/services/
  crawler_config_service.py
  crawl_runner_service.py
  crawler_scheduler_service.py
```

删除或废弃：

```text
downloader/
diff/
zone_sources 配置入口
Zone 相关 Pipeline 分支
```

第一阶段可以不物理删除旧代码，但 UI 和运行路径不再引用 Zone。后续确认稳定后再清理文件。

## Scrapling 抓取器设计

### CrawlResult

```python
@dataclass(frozen=True)
class SourceDomain:
    domain: str
    tld: str
    source_status: str
    dropped_date: str | None
    metrics: dict[str, str]

@dataclass(frozen=True)
class CrawlResult:
    tld: str
    pages_fetched: int
    domains_seen: int
    available_domains: list[SourceDomain]
```

### 抓取逻辑

```text
login_if_needed()
build_deleted_tld_url(tld)
for page in range(max_pages):
    fetch page
    detect block/captcha/login
    parse table
    keep rows where status == available
    sleep request_delay_seconds + jitter
    follow next page
```

### 页面异常检测

检测：

- 登录页跳转。
- HTTP 403/429。
- 页面包含 captcha/verify/checking 字样。
- 表格不存在。
- 表头无法识别。

处理：

- 保存 HTML 快照到 `runtime/data/snapshots/{run_id}/{tld}-{page}.html`。
- 标记当前 run failed。
- 更新账号/代理状态。

## API 设计

### 配置

```text
GET  /api/crawler/config
PUT  /api/crawler/config
```

返回账号、代理、TLD 调度、保留策略。secret 字段返回 `********`。

### 测试账号

```text
POST /api/crawler/accounts/{id}/test
```

功能：

- 使用账号绑定代理或默认代理。
- 尝试登录 ExpiredDomains.net。
- 成功后更新账号状态 `healthy`。

### 测试代理

```text
POST /api/crawler/proxies/{id}/test
```

功能：

- 只测试代理能否访问 ExpiredDomains.net。
- 不做登录。

### 测试抓取第一页

```text
POST /api/crawler/tlds/{tld}/test-fetch
```

功能：

- 使用账号池选择一个账号。
- 抓取该 TLD 第一页。
- 解析但不进入完整评分流程。
- 可选择 `dry_run=true`，只返回解析结果不落库。

### 启动 TLD 任务

```text
POST /api/crawler/tlds/{tld}/run
```

功能：

- 启动单个 TLD 抓取 + 评分流程。
- 如果已有任务运行，根据现有重启逻辑取消后重启。

### 停止任务

复用现有：

```text
POST /api/jobs/stop
```

## 前端设计

### 导航

保留当前导航：

- 仪表盘
- 候选域名
- 配置

不新增独立“任务”侧边栏。

### 配置页结构

配置页分组调整为：

1. 运行路径
2. 数据源账号
3. 代理池
4. 后缀爬取计划
5. 域名过滤规则
6. 评分与查询
7. 大模型评分
8. 邮件通知

删除 Zone 数据源配置。

### 数据源账号 UI

表格字段：

- 启用
- 用户名
- 密码
- 绑定代理
- 状态
- 最近错误
- 操作

操作：

- 添加账号
- 删除账号
- 测试登录
- 重置状态

状态 badge：

- 正常
- 冷却
- 登录失败
- 访问受限
- 验证码
- 禁用

### 代理池 UI

表格字段：

- 启用
- 名称
- 代理 URL
- 状态
- 最近错误
- 操作

操作：

- 添加代理
- 删除代理
- 测试代理
- 重置状态

代理 URL 输入框使用 password 类型或局部遮罩，避免认证信息裸露。

### 后缀爬取计划 UI

表格字段：

- 启用
- 后缀
- 每日爬取时间
- 最大页数
- 请求间隔秒数
- 操作

操作：

- 添加后缀计划
- 删除
- 测试抓取第一页
- 立即运行该后缀

后缀输入建议支持：

- 常见 TLD 下拉选择。
- 自定义输入。

### 仪表盘

新增指标：

- 今日抓取源域名数。
- 今日页面初筛可注册数。
- 今日完成 TLD 数。
- 最近抓取失败数。

最近任务表增加：

- TLD。
- 账号。
- 代理。
- 抓取页数。
- 初筛可注册数。

### 候选域名页

临时过滤来源改为今日 `deleted_domain_sources`。

说明文案：

```text
只读取今日抓取的 ExpiredDomains.net 源数据重新过滤和评分，不重新抓取网页，不发送通知。
```

## Pipeline 改造

当前 Pipeline 需要拆成两步：

```text
CrawlRunner
  -> 抓取并写入 deleted_domain_sources

PipelineService
  -> 从 deleted_domain_sources 读取今日 source rows
  -> 过滤、评分、二次可注册、Wayback、通知
```

`PipelineService.run()` 不再接收 zone 文件，也不再做 `diff_deleted_domains`。

建议新增：

```python
async def run_from_source_rows(
    tld: str | None,
    source_date: date,
    source: str,
    job_id: int,
) -> PipelineResult:
    ...
```

## 任务失败与重试

沿用现有失败处理：

- job failed。
- 保留 error。
- 定时任务按配置重试。
- 最终失败后邮件通知。
- 服务启动时清理 stale running job。

新增抓取类错误分类：

```text
login_failed
captcha_required
rate_limited
proxy_failed
parse_failed
network_timeout
```

其中：

- `captcha_required` 不建议自动重试。
- `login_failed` 不建议自动重试同账号。
- `proxy_failed` 可以换代理或换账号后重试。
- `network_timeout` 可以按现有重试机制处理。

## 开发步骤

### 阶段 1：数据模型和配置页

1. 新增数据库表。
2. 新增 crawler config service。
3. 前端配置页删除 Zone 配置。
4. 前端新增账号池、代理池、TLD 调度。
5. API 返回 secret mask。

验收：

- 可以新增账号。
- 可以新增代理。
- 可以新增多个 TLD 调度。
- 刷新页面配置不丢。

### 阶段 2：Scrapling 登录和测试连接

1. 引入 Scrapling 依赖。
2. 实现代理测试。
3. 实现账号测试登录。
4. 保存 session/cookie。
5. 处理登录失败、验证码、403、429。

验收：

- 单个账号能测试登录。
- 代理能测试连通性。
- 失败状态能显示在前端。

### 阶段 3：单 TLD 第一页抓取

1. 实现 URL 构造。
2. 实现第一页抓取。
3. 实现表格解析。
4. 保存页面快照。
5. dry run 返回前端预览。

验收：

- `.com` 测试抓取第一页能返回域名列表。
- 只保留 source status 为 available 的域名。

### 阶段 4：分页和落库

1. 支持 max_pages。
2. 支持 request_delay_seconds + jitter。
3. 支持下一页。
4. 落库 `deleted_domain_sources`。
5. 抓取前清理旧源数据。

验收：

- 手动运行某 TLD 后，今日源数据入库。
- 第二天或模拟日期运行时旧源数据会被清理。

### 阶段 5：接入评分流程

1. Pipeline 从 source rows 读取域名。
2. 复用现有过滤规则。
3. 复用 AI/本地评分。
4. 复用可注册二次查询。
5. 复用 Wayback。
6. 复用邮件通知。

验收：

- 手动运行某 TLD 后，候选域名页能看到最终候选。
- 邮件通知正常。

### 阶段 6：多 TLD 调度

1. 调度器支持每 TLD cron。
2. 配置变更后 reload 调度。
3. 仪表盘显示 TLD 抓取运行情况。

验收：

- `.com` 和 `.net` 可以配置不同时间。
- 到点分别触发。

### 阶段 7：删除 Zone 入口

1. 删除前端 Zone 配置。
2. 删除后端 Zone source 使用路径。
3. README 更新为 ExpiredDomains.net 方案。
4. 保留旧代码文件或彻底删除，按实际风险决定。

验收：

- UI 中没有 Zone 概念。
- 运行流程不再访问 Zone。

## 测试计划

后端单元测试：

- 配置保存和 secret mask。
- 账号池选择逻辑。
- 代理选择逻辑。
- 账号状态流转。
- TLD 调度注册和删除。
- 源数据清理。
- parser 解析固定 HTML fixture。
- captcha/403/429 检测。
- Pipeline 从 source rows 运行。

前端验证：

- 账号池增删改。
- 代理池增删改。
- 后缀计划增删改。
- 测试登录按钮反馈。
- 测试代理按钮反馈。
- 测试抓取第一页反馈。
- 移动端输入不溢出。

集成验证：

- Docker 构建。
- 后端健康检查。
- 配置保存后刷新不丢。
- 单 TLD 手动抓取。
- 候选页临时过滤。
- 邮件测试和失败通知。

## 风险

1. ExpiredDomains.net 页面结构变化。
   - 用 HTML fixture 测试 parser。
   - 保存失败快照。

2. 登录和验证码。
   - 不绕过验证码。
   - 前端显示账号状态，提示人工处理。

3. 可注册状态滞后。
   - 必须做二次可注册查询。

4. 账号封禁。
   - 低频访问。
   - 固定账号代理绑定。
   - 不做高频轮换。

5. 不同 TLD 更新时间不稳定。
   - 每 TLD 独立调度。
   - 支持手动立即运行。

## 默认值

```text
max_pages = 20
request_delay_seconds = 12
request_delay_jitter_seconds = 5
expireddomains_keep_days = 1
global_concurrency = 1
failure_retry_count = 2
failure_retry_delay_seconds = 300
```

## 第一版验收标准

- 配置页没有 Zone 配置。
- 可以配置多个 ExpiredDomains.net 账号。
- 可以配置多个代理。
- 账号可以绑定代理。
- 可以配置多个 TLD，每个 TLD 有独立每日爬取时间。
- 可以测试代理。
- 可以测试账号登录。
- 可以测试抓取某 TLD 第一页。
- 手动运行某 TLD 能把今日 available 源域名落库。
- 候选域名页能基于今日源数据临时过滤。
- 完整任务能完成评分、二次可注册查询、Wayback、邮件通知。
