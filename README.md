# domain_hunter

Python 域名发现系统，用于抓取 ExpiredDomains.net 每日更新的已删除且页面初筛可注册域名，进行规则过滤、评分、可注册二次查询、Wayback 历史检查和邮件通知。

## 功能

- ExpiredDomains.net 数据源：支持多账号、代理池、账号绑定代理。
- 多后缀独立调度：不同 TLD 可配置不同每日爬取时间。
- 每日源数据落库：默认只保留今日源数据，第二天抓取前清理旧源数据。
- 插件式过滤：长度、仅字母、无数字、无连字符、元音和连续辅音规则。
- 本地/AI 评分：配置 OpenAI 兼容接口后优先 AI 评分，失败自动回退本地评分。
- 可注册二次查询：页面 available 只作为初筛，最终仍通过系统配置的查询方式确认。
- Wayback 历史检查：采样 CDX 结果并标记常见垃圾关键词。
- SQLite 落库：源数据、候选、评分、历史、任务和抓取运行记录。
- FastAPI 后端和 React 前端。
- APScheduler 定时运行，Docker Compose 单机部署。

## Docker 部署

```powershell
docker compose up -d --build
```

访问：

```text
Frontend: http://localhost:8080
Backend:  http://localhost:8000
```

查看日志：

```powershell
docker compose logs -f backend
```

停止服务：

```powershell
docker compose down
```

运行数据保存在 `runtime/`，包括 SQLite、data、cache 和抓取页面快照。

## 配置

默认运行目录：

- 运行目录：`runtime`
- 数据库：`runtime/database/domain_hunter.sqlite3`
- 数据目录：`runtime/data`
- 缓存目录：`runtime/cache`

运行目录可在前端配置页维护。数据库、数据目录和缓存目录固定在运行目录下派生。

业务配置保存在 SQLite `settings` 表，可在前端配置页维护：

- ExpiredDomains.net 账号池。
- 代理池。
- 后缀爬取计划，每个后缀独立每日时间、最大页数和请求间隔。
- 域名过滤规则。
- 可注册查询方式、并发和超时。
- Wayback 开关与超时。
- 候选数量与最低分。
- 大模型评分配置。
- SMTP 邮件配置。
- 定时任务开关和失败重试配置。

## 反爬边界

系统只做低频、可恢复、失败可见的抓取：

- 单任务低并发。
- 固定账号和代理绑定。
- 请求间隔和最大页数限制。
- 登录失效、403、429、验证码时停止任务并提示人工处理。

系统不做验证码绕过、高频代理轮换、自动注册账号或封禁规避式代理池。
