from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.services.config_service import ConfigService
from backend.services.pipeline_service import PipelineService
from config import get_settings
from database import Database


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
    return await db.stats()


@app.get("/api/domains")
async def domains(limit: int = 100, status: str | None = None, search: str | None = None) -> list[dict]:
    db = _db()
    await db.init()
    return await db.list_candidates(limit=limit, status=status, search=search)


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
    job_id = await db.create_job("api")
    background_tasks.add_task(_run_background_job, job_id, payload or {})
    return {"job_id": job_id, "status": "running"}


@app.post("/api/jobs/upload")
async def upload_deleted_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict:
    db = _db()
    await db.init()
    suffix = Path(file.filename or "deleted.txt").suffix or ".txt"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        temp.write(content)
        temp.close()
        job_id = await db.create_job("upload")
        background_tasks.add_task(_run_background_job, job_id, {"deleted_file": temp.name})
        return {"job_id": job_id, "status": "running"}
    except Exception:
        Path(temp.name).unlink(missing_ok=True)
        raise


async def _run_background_job(job_id: int, payload: dict) -> None:
    db = _db()
    await db.init()
    config = await ConfigService(db).get_config()
    service = PipelineService(db, config)
    deleted_file = Path(payload["deleted_file"]) if payload.get("deleted_file") else None
    try:
        await service.run(
            deleted_file=deleted_file,
            source="api",
            top=_optional_int(payload.get("top")),
            min_score=_optional_int(payload.get("min_score")),
            create_job=False,
            job_id=job_id,
        )
    finally:
        if deleted_file and str(deleted_file).startswith(tempfile.gettempdir()):
            deleted_file.unlink(missing_ok=True)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
