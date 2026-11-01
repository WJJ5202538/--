from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.config import OUTPUT_DIR
from app.grading_adapter import grade
from app.jobs import JobStore
from app.services.annotator import AnnotationError
from app.services.extractor import ExtractionError

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """A failure whose message is safe to show to the user."""


def process_job(job_id: str, store: JobStore) -> None:
    job = store.get(job_id)
    if job is None:
        return

    store.mark_processing(job_id)
    output_path = OUTPUT_DIR / f"{job_id}.docx"

    try:
        result = grade(job.source_path, output_path, job.source_type)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise ProcessingError("批注稿没有成功生成，请重试。")

        _save_extraction_sidecars(job_id, result)
        store.complete(
            job_id,
            output_name=_output_filename(job.original_name),
            output_path=output_path,
            issue_count=result.issue_count,
            engine=result.engine,
        )
    except (ExtractionError, AnnotationError, ProcessingError) as exc:
        _remove_failed_output(output_path)
        store.fail(job_id, str(exc))
    except Exception:
        logger.exception("Unexpected failure while processing job %s", job_id)
        _remove_failed_output(output_path)
        store.fail(job_id, "处理文档时出现意外错误，请重试或更换文件。")


def _output_filename(original_name: str) -> str:
    stem = Path(original_name).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
    if not stem:
        stem = "文档"
    if len(stem) > 80:
        stem = stem[:80].rstrip()
    return f"{stem}_批注.docx"


def _save_extraction_sidecars(job_id: str, result) -> None:
    """Keep JSON/Markdown outputs for debugging and module hand-off."""
    if result.extraction is None:
        return
    try:
        json_path = OUTPUT_DIR / f"{job_id}.extraction.json"
        md_path = OUTPUT_DIR / f"{job_id}.extraction.md"
        json_path.write_text(
            json.dumps(result.extraction.as_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(result.extraction.markdown, encoding="utf-8")
    except OSError:
        logger.warning("Could not write extraction sidecars for %s", job_id, exc_info=True)


def _remove_failed_output(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove incomplete output %s", path, exc_info=True)