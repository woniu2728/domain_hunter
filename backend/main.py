from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.services.config_service import ConfigService
from backend.services.job_runner_service import job_runner_service
from backend.services.scheduler_service import scheduler_service
from config import get_settings
from database import Database
from domain_hunter.types import AppConfig
from filters import DefaultDomainFilter, filter_domains
from notifier import send_test_email
from scorer.ai_score import score_domains_for_config, test_llm_scoring


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
    data.update(await db.zone_diff_stats())
    return data


@app.get("/api/domains")
async def domains(limit: int = 100, status: str | None = None, search: str | None = None) -> list[dict]:
    db = _db()
    await db.init()
    return await db.list_candidates(limit=limit, status=status, search=search)


@app.post("/api/domains/preview")
async def preview_domains(payload: dict) -> dict:
    db = _db()
    await db.init()
    stored_config = await ConfigService(db).get_config()
    config = _preview_config(payload, stored_config)
    tlds = _preview_tlds(payload)
    raw_domains = await db.list_zone_diff_domains(
        limit=int(payload.get("source_limit", 5000)),
        tlds=tlds,
        search=str(payload.get("search") or "").strip() or None,
    )
    filtered = filter_domains(raw_domains, filters=(_preview_filter(config, tlds),))
    min_score = int(payload.get("min_score", config.min_score))
    top_candidates = int(payload.get("top_candidates", config.top_candidates))
    scored = await score_domains_for_config(filtered, config)
    scores = [score for score in scored if score.total_score >= min_score][:top_candidates]
    return {
        "total_source": len(raw_domains),
        "total_filtered": len(filtered),
        "total_scored": len(scores),
        "items": [
            {
                "domain": score.domain,
                "total_score": score.total_score,
                "reasons": ", ".join(score.reasons),
                "status": "preview",
                "notes": "临时预览，未查询可注册状态",
                "archive": None,
                "spam": None,
            }
            for score in scores
        ],
    }


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


def _preview_config(payload: dict, base_config: AppConfig) -> AppConfig:
    values = base_config.__dict__.copy()
    for key in (
        "filter_min_length",
        "filter_max_length",
        "filter_letters_only",
        "filter_require_vowel",
        "filter_no_digits",
        "filter_no_hyphen",
        "filter_max_consecutive_consonants",
        "top_candidates",
        "min_score",
    ):
        if key in payload:
            current = values[key]
            values[key] = _coerce_preview_value(payload[key], current)
    return AppConfig(**values)


def _preview_filter(config: AppConfig, tlds: list[str]) -> DefaultDomainFilter:
    return DefaultDomainFilter(
        min_length=config.filter_min_length,
        max_length=config.filter_max_length,
        allowed_tlds=tuple(tlds),
        letters_only=config.filter_letters_only,
        require_vowel=config.filter_require_vowel,
        no_digits=config.filter_no_digits,
        no_hyphen=config.filter_no_hyphen,
        max_consecutive_consonants=config.filter_max_consecutive_consonants,
    )


def _preview_tlds(payload: dict) -> list[str]:
    raw = str(payload.get("tlds", "")).strip()
    if not raw:
        return []
    return [item.strip().lower().lstrip(".") for item in raw.split(",") if item.strip()]


def _coerce_preview_value(value: object, current: object) -> object:
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int):
        return int(value)
    return value
