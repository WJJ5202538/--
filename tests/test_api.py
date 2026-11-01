from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from helpers import docx_bytes, pdf_bytes

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def upload_and_wait(client: TestClient, filename: str, content: bytes, content_type: str):
    response = client.post(
        "/api/jobs",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 202, response.text
    job = response.json()
    for _ in range(80):
        current = client.get(f"/api/jobs/{job['id']}")
        assert current.status_code == 200
        if current.json()["status"] in {"completed", "failed"}:
            return current.json()
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_homepage_and_config(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "上传文档" in page.text
    assert page.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in page.headers["content-security-policy"]

    config = client.get("/api/config").json()
    assert config["max_upload_mb"] >= 1
    assert config["allowed_extensions"] == ["docx", "pdf"]


def test_upload_annotate_and_download_docx(client: TestClient) -> None:
    source = docx_bytes(["作业：7 + 8 = 16。", "3 + 3 = 6。"])

    job = upload_and_wait(
        client,
        "数学作业.docx",
        source,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert job["status"] == "completed", job
    assert job["issue_count"] == 1
    assert job["output_name"] == "数学作业_批注.docx"
    assert job["download_url"].endswith("/download")

    response = client.get(job["download_url"])
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert "filename*=utf-8''" in response.headers["content-disposition"].lower()


def test_upload_pdf_produces_docx(client: TestClient) -> None:
    job = upload_and_wait(client, "练习.pdf", pdf_bytes("4 + 5 = 10"), "application/pdf")
    assert job["status"] == "completed", job
    assert job["issue_count"] == 1
    assert job["output_name"] == "练习_批注.docx"
    assert client.get(job["download_url"]).status_code == 200


def test_rejects_unsupported_and_fake_files(client: TestClient) -> None:
    unsupported = client.post("/api/jobs", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert unsupported.status_code == 415

    fake_docx = client.post(
        "/api/jobs",
        files={
            "file": (
                "fake.docx",
                b"not a zip",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert fake_docx.status_code == 400


def test_unknown_job(client: TestClient) -> None:
    assert client.get("/api/jobs/" + "0" * 32).status_code == 404
    assert client.get("/api/jobs/not-a-job").status_code == 404
