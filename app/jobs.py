from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class Job:
    id: str
    original_name: str
    source_path: Path
    source_type: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())
    output_name: str | None = None
    output_path: Path | None = None
    issue_count: int | None = None
    engine: str | None = None
    error: str | None = None

    def public(self) -> dict:
        download_url = f"/api/jobs/{self.id}/download" if self.status == "completed" else None
        return {
            "id": self.id,
            "original_name": self.original_name,
            "source_type": self.source_type,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "output_name": self.output_name,
            "download_url": download_url,
            "issue_count": self.issue_count,
            "engine": self.engine,
            "error": self.error,
        }


class JobStore:
    """Small in-memory job store for a single-process deployment."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}

    def create(self, *, job_id: str, original_name: str, source_path: Path, source_type: str) -> Job:
        with self._lock:
            job = Job(
                id=job_id,
                original_name=original_name,
                source_path=source_path,
                source_type=source_type,
            )
            self._jobs[job_id] = job
            return copy.copy(job)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return copy.copy(job) if job else None

    def mark_processing(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "processing"
                job.updated_at = _now()

    def complete(
        self,
        job_id: str,
        *,
        output_name: str,
        output_path: Path,
        issue_count: int | None,
        engine: str,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "completed"
                job.output_name = output_name
                job.output_path = output_path
                job.issue_count = issue_count
                job.engine = engine
                job.updated_at = _now()

    def fail(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "failed"
                job.error = message
                job.updated_at = _now()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")