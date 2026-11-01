from __future__ import annotations

import logging
import re
import uuid
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    ALLOWED_EXTENSIONS,
    BASE_DIR,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    OUTPUT_DIR,
    UPLOAD_DIR,
)
from app.grading_adapter import ENGINE_NAME
from app.jobs import JobStore
from app.services.pipeline import process_job

logger = logging.getLogger(__name__)
STATIC_DIR = BASE_DIR / "app" / "static"
STORE = JobStore()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="文批 DocMark",
    description="上传 Word/PDF，下载带红色 # 计算的批注稿。",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    )
    return response


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
async def config() -> dict:
    return {
        "max_upload_mb": MAX_UPLOAD_MB,
        "allowed_extensions": sorted(extension.lstrip(".") for extension in ALLOWED_EXTENSIONS),
        "engine": ENGINE_NAME,
    }


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/jobs", status_code=202)
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
) -> JSONResponse:
    original_name = _safe_display_name(file.filename or "")
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="仅支持 .docx（Word）和 .pdf 文件。")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES + 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {MAX_UPLOAD_MB} MB。")

    job_id = uuid.uuid4().hex
    source_path = UPLOAD_DIR / f"{job_id}{suffix}"
    total = 0

    try:
        with source_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"文件不能超过 {MAX_UPLOAD_MB} MB。")
                destination.write(chunk)
    except HTTPException:
        source_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        source_path.unlink(missing_ok=True)
        logger.exception("Could not save upload")
        raise HTTPException(status_code=500, detail="文件保存失败，请重试。") from exc
    finally:
        await file.close()

    if total == 0:
        source_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件是空的，请重新选择。")

    validation_error = _validate_file(source_path, suffix)
    if validation_error:
        source_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=validation_error)

    job = STORE.create(
        job_id=job_id,
        original_name=original_name,
        source_path=source_path,
        source_type=suffix.lstrip("."),
    )
    background_tasks.add_task(process_job, job_id, STORE)
    return JSONResponse(job.public(), status_code=202)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(status_code=404, detail="任务不存在。")
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或服务已重启，请重新上传。")
    return job.public()


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str) -> FileResponse:
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或服务已重启，请重新上传。")
    if job.status != "completed" or job.output_path is None or job.output_name is None:
        raise HTTPException(status_code=409, detail="批注稿尚未生成。")

    path = job.output_path.resolve()
    if OUTPUT_DIR not in path.parents or not path.is_file():
        raise HTTPException(status_code=410, detail="批注稿已不存在，请重新上传。")

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=job.output_name,
        headers={"Cache-Control": "no-store"},
    )


def _safe_display_name(raw: str) -> str:
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(character for character in name if character.isprintable()).strip()
    if not name:
        return "未命名文档"
    return name[:180]


def _validate_file(path: Path, suffix: str) -> str | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(8)
    except OSError:
        return "文件读取失败，请重新上传。"

    if suffix == ".pdf":
        if not header.startswith(b"%PDF-"):
            return "文件内容不是有效的 PDF。"
        return None

    if not header.startswith(b"PK"):
        return "文件内容不是有效的 .docx 文件。"
    try:
        if not zipfile.is_zipfile(path):
            return "Word 文件已损坏，请重新导出后再上传。"
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                return "文件不是标准的 .docx 文档。"
            expanded_size = sum(info.file_size for info in archive.infolist())
            if expanded_size > 300 * 1024 * 1024:
                return "Word 文件解压后体积过大，请拆分后再上传。"
    except (zipfile.BadZipFile, OSError):
        return "Word 文件已损坏，请重新导出后再上传。"
    return None


# Keep an explicit handler so API clients always receive Chinese JSON errors.
@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求处理失败。"
    return JSONResponse({"detail": detail}, status_code=exc.status_code)