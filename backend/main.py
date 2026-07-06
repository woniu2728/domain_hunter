from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.services.config_service import ConfigService
from backend.services.crawl_runner_service import test_account, test_fetch_first_page, test_proxy
from backend.services.job_runner_service import job_runner_service
from backend.services.scheduler_service import scheduler_service
from config import get_settings
from database import Database
from notifier import send_test_email
from scorer.ai_score import test_llm_scoring


app = FastAPI(title="Domain Hunter API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db() -> Database:
    settings = get_settings()
    settings.ensure_dirs()
    return Database(settings.database_url)


@app.on_event("startup")
async def startup() -> None:
    db = _db()
    await db.init()
    job_runner_service.start(_db)
    await job_runner_service.cleanup_stale_running()
    await scheduler_service.start(_db)
    await scheduler_service.reload()


@app.on_event("shutdown")
async def shutdown() -> None:
    await job_runner_service.shutdown()
    scheduler_service.shutdown()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
async def get_config() -> dict:
    db = _db()
    await db.init()
    return await ConfigService(db).public_config()


@app.put("/api/config")
async def update_config(payload: dict) -> dict:
    db = _db()
    await db.init()
    config = await ConfigService(db).update_config(payload)
    await scheduler_service.reload(config)
    return config.masked()


@app.post("/api/config/test-email")
async def test_email() -> dict[str, str]:
    db = _db()
    await db.init()
    config = await ConfigService(db).get_config()
    try:
        await send_test_email(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"测试邮件发送失败：{exc}") from exc
    return {"status": "sent"}


@app.post("/api/config/test-llm")
async def test_llm() -> dict[str, object]:
    db = _db()
    await db.init()
    config = await ConfigService(db).get_config()
    try:
        score = await test_llm_scoring(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型评分测试失败：{exc}") from exc
    return {
        "domain": score.domain,
        "score": score.total_score,
        "reasons": list(score.reasons),
    }


@app.get("/api/stats")
async def stats() -> dict:
    db = _db()
    await db.init()
    data = await db.stats()
    data.update(await db.source_domain_stats(date.today().isoformat()))
    data.update(await db.crawler_run_stats())
    return data


@app.get("/api/domains")
async def domains(limit: int = 100, status: str | None = None, search: str | None = None, tld: str | None = None) -> list[dict]:
    db = _db()
    await db.init()
    return await db.list_candidates(limit=limit, status=status, search=search, tld=tld)


@app.get("/api/jobs")
async def jobs(limit: int = 50) -> list[dict]:
    db = _db()
    await db.init()
    return [job.__dict__ for job in await db.list_jobs(limit=limit)]


@app.get("/api/jobs/{job_id}")
async def job(job_id: int) -> dict:
    db = _db()
    await db.init()
    item = await db.get_job(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return item.__dict__


@app.post("/api/jobs/run")
async def run_job(payload: dict | None = None) -> dict:
    try:
        job_id = await job_runner_service.restart(source="api", payload=payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job_id": job_id, "status": "running"}


@app.post("/api/jobs/stop")
async def stop_job() -> dict[str, str]:
    await job_runner_service.cancel_running("用户手动停止任务")
    return {"status": "cancelled"}


@app.post("/api/crawler/accounts/{account_id}/test")
async def test_crawler_account(account_id: str) -> dict[str, str]:
    db = _db()
    await db.init()
    try:
        await test_account(db, account_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"账号测试失败：{exc}") from exc
    return {"status": "ok"}


@app.post("/api/crawler/proxies/{proxy_id}/test")
async def test_crawler_proxy(proxy_id: str) -> dict[str, str]:
    db = _db()
    await db.init()
    try:
        await test_proxy(db, proxy_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"代理测试失败：{exc}") from exc
    return {"status": "ok"}


@app.post("/api/crawler/tlds/{tld}/test-fetch")
async def test_crawler_tld(tld: str) -> dict:
    db = _db()
    await db.init()
    try:
        return await test_fetch_first_page(db, tld)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"测试抓取失败：{exc}") from exc
