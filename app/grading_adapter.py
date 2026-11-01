from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.annotator import annotate_docx, create_annotated_docx_from_pdf
from app.services.extractor import ExtractedDocument, extract_document

ENGINE_NAME = "内置演示引擎"


@dataclass
class GradeResult:
    engine: str
    issue_count: int | None = None
    extraction: ExtractedDocument | None = None


def grade(source: Path, output: Path, source_type: str) -> GradeResult:
    """Adapter between the web app and the document-grading modules.

    Replace the body of this function with calls to your existing modules.
    A typical integration looks like this:

        from my_extractor import extract
        from my_annotator import annotate

        extracted = extract(str(source))          # -> JSON + Markdown
        annotate(str(source), extracted, str(output))

        return GradeResult(engine="我的批改模块", issue_count=..., extraction=...)

    The source argument is the uploaded .docx/.pdf, and output must be the
    final .docx file to download. Raise an Exception with a user-facing
    Chinese message if grading cannot be completed.
    """
    extracted = extract_document(source)

    if source_type == "docx":
        issue_count = annotate_docx(source, output)
    elif source_type == "pdf":
        issue_count = create_annotated_docx_from_pdf(extracted, output)
    else:
        raise ValueError("不支持的文件类型。")

    return GradeResult(
        issue_count=issue_count,
        engine=ENGINE_NAME,
        extraction=extracted,
    )
