from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.services.config_service import ConfigService
from backend.services.pipeline_service import PipelineService
from config import get_settings
from database import Database
from domain_hunter.types import AppConfig
from filters import DefaultDomainFilter, filter_domains
from scorer import score_domains


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
    await _db().init()


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
    return config.masked()


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
    config = _preview_config(payload)
    tlds = _preview_tlds(payload)
    raw_domains = await db.list_zone_diff_domains(
        limit=int(payload.get("source_limit", 5000)),
        tlds=tlds,
        search=str(payload.get("search") or "").strip() or None,
    )
    filtered = filter_domains(raw_domains, filters=(_preview_filter(config, tlds),))
    min_score = int(payload.get("min_score", config.min_score))
    top_candidates = int(payload.get("top_candidates", config.top_candidates))
    scores = [score for score in score_domains(filtered) if score.total_score >= min_score][:top_candidates]
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
async def run_job(background_tasks: BackgroundTasks, payload: dict | None = None) -> dict:
    db = _db()
    await db.init()
    if await db.has_running_job():
        raise HTTPException(status_code=409, detail="已有任务正在运行，请等待完成后再启动。")
    config = await ConfigService(db).get_config()
    if not _has_enabled_zone_source(config.zone_sources):
        raise HTTPException(status_code=400, detail="请先在配置中添加启用的 Zone 来源。")
    job_id = await db.create_job("api")
    background_tasks.add_task(_run_background_job, job_id, payload or {})
    return {"job_id": job_id, "status": "running"}


async def _run_background_job(job_id: int, payload: dict) -> None:
    db = _db()
    await db.init()
    config = await ConfigService(db).get_config()
    service = PipelineService(db, config)
    deleted_file = Path(payload["deleted_file"]) if payload.get("deleted_file") else None
    await service.run(
        deleted_file=deleted_file,
        source="api",
        top=_optional_int(payload.get("top")),
        min_score=_optional_int(payload.get("min_score")),
        create_job=False,
        job_id=job_id,
    )


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _has_enabled_zone_source(sources: list[dict]) -> bool:
    return any(source.get("enabled") and source.get("tld") and source.get("zone_url") for source in sources)


def _preview_config(payload: dict) -> AppConfig:
    defaults = AppConfig()
    values = defaults.__dict__.copy()
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
