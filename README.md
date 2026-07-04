# domain_hunter

根据 `Python_域名发现系统设计.md` 实现的 Python 域名发现系统 MVP，用于从多个后缀的 Zone 差分或已删除域名列表中筛选、评分、查询可注册状态，并进行 Wayback 历史检查和通知。

## 功能

- 支持多个后缀的 Zone 文件差分：昨天集合减今天集合。
- 插件式过滤：长度 4-12、仅字母、无数字、无连字符、至少一个元音、无连续四个辅音。
- 品牌评分：短域名、纯字母、AI 关键词、字典词、可发音、双词组合等规则。
- SQLite 落库：`domains`、`score`、`history`。
- FastAPI 后端：配置、任务、候选域名、统计接口。
- React 前端：Dashboard、Candidates、Jobs、Config。
- Availability 查询：默认 `mock`，可切到 Verisign RDAP。
- Wayback 历史检查：采样 CDX 结果并标记常见垃圾关键词。
- 通知：配置 SMTP 后发送邮件，否则输出 Rich 表格。
- APScheduler 定时入口。
- Docker Compose 单机部署。

## 安装

```powershell
python -m pip install -r requirements.txt
```

应用自带默认数据库、数据目录和缓存目录；所有配置均可在前端 Config 页面维护。

## 使用

初始化数据库：

```powershell
python app.py init-db
```

使用已删除域名列表运行：

```powershell
python app.py run --deleted-file data/sample_deleted.txt --top 20 --min-score 40
```

使用两个 Zone 文件差分运行：

```powershell
python app.py run --yesterday-zone data/com-zone-yesterday.txt --today-zone data/com-zone-today.txt
```

启动每日定时任务，默认北京时间 02:00：

```powershell
python app.py schedule --hour 2 --minute 0
```

启动后端 API：

```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

启动前端：

```powershell
cd frontend
npm install
npm run dev
```

本地开发时，前端默认通过同源 `/api` 调用后端；Docker 部署时由 Nginx 反向代理。

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

运行数据会保存在 `runtime/`，包括 SQLite、data、cache。

## 配置

默认路径：

- 数据库：`runtime/database/domain_hunter.sqlite3`
- 数据目录：`runtime/data`
- 缓存目录：`runtime/cache`

这些路径也可在前端 Config 页面维护，保存后写入 `runtime/app_settings.json`，后续启动会读取该文件。

业务配置会存入后端 SQLite `settings` 表，也可在前端 Config 页面维护：

- 数据库路径、数据目录、缓存目录。
- 多个后缀的 Zone 来源、Bearer Token 和启用状态。
- Availability 并发与超时。
- Wayback 开关与超时。
- 候选数量与最低分。
- SMTP 邮件配置。
- 定时任务配置。

## 目录

```text
domain_hunter/
├── app.py
├── config.py
├── scheduler.py
├── backend/
├── frontend/
├── docker/
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
