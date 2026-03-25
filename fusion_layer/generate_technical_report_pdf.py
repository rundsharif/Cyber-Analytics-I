"""Generate a PDF from the fusion technical report markdown without external dependencies."""

from __future__ import annotations

from pathlib import Path
import re
import textwrap


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN_X = 54
MARGIN_TOP = 64
MARGIN_BOTTOM = 60
LINE_HEIGHT = 14
FONT_SIZE = 11
WRAP_WIDTH = 92


def _to_ascii(value: str) -> str:
    """Normalize text to ASCII-friendly output for a simple PDF writer."""

    replacements = {
        "•": "-",
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "’": "'",
        "<=": "<=",
        ">=": ">=",
    }
    normalized = value
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized.encode("ascii", errors="replace").decode("ascii")


def _escape_pdf_text(value: str) -> str:
    """Escape a text line for PDF text operators."""

    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _markdown_to_lines(markdown_text: str) -> list[str]:
    """Convert markdown content into wrapped plain-text lines suitable for PDF output."""

    lines: list[str] = []
    in_code_block = False

    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            lines.append("")
            continue

        if in_code_block:
            wrapped = textwrap.wrap(f"    {raw_line.rstrip()}", width=WRAP_WIDTH) or [""]
            lines.extend(wrapped)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", raw_line)
        if heading_match:
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            if level == 1:
                lines.append(heading.upper())
                lines.append("=" * min(len(heading), WRAP_WIDTH))
            elif level == 2:
                lines.append(heading)
                lines.append("-" * min(len(heading), WRAP_WIDTH))
            else:
                lines.append(heading)
            lines.append("")
            continue

        bullet_match = re.match(r"^\s*[-*]\s+(.*)$", raw_line)
        if bullet_match:
            bullet_text = f"- {bullet_match.group(1).strip()}"
            wrapped = textwrap.wrap(
                bullet_text,
                width=WRAP_WIDTH,
                subsequent_indent="  ",
            ) or [""]
            lines.extend(wrapped)
            continue

        ordered_match = re.match(r"^\s*(\d+)\.\s+(.*)$", raw_line)
        if ordered_match:
            numbered_text = f"{ordered_match.group(1)}. {ordered_match.group(2).strip()}"
            wrapped = textwrap.wrap(
                numbered_text,
                width=WRAP_WIDTH,
                subsequent_indent="   ",
            ) or [""]
            lines.extend(wrapped)
            continue

        if not stripped:
            lines.append("")
            continue

        wrapped = textwrap.wrap(raw_line.strip(), width=WRAP_WIDTH) or [""]
        lines.extend(wrapped)

    return [_to_ascii(line) for line in lines]


def _paginate(lines: list[str]) -> list[list[str]]:
    """Split lines into fixed-size pages."""

    usable_height = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    lines_per_page = max(1, usable_height // LINE_HEIGHT)
    return [lines[index : index + lines_per_page] for index in range(0, len(lines), lines_per_page)]


def _build_pdf_bytes(pages: list[list[str]]) -> bytes:
    """Create a minimal PDF document with Helvetica text pages."""

    if not pages:
        pages = [["(empty)"]]

    objects: list[bytes] = []

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")  # 1
    objects.append(b"<< /Type /Pages /Kids [] /Count 0 >>")  # 2 placeholder
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")  # 3

    page_object_ids: list[int] = []

    for page_lines in pages:
        page_object_id = len(objects) + 1
        content_object_id = page_object_id + 1
        page_object_ids.append(page_object_id)

        y_start = PAGE_HEIGHT - MARGIN_TOP
        text_lines = [
            "BT",
            f"/F1 {FONT_SIZE} Tf",
            f"{MARGIN_X} {y_start} Td",
        ]

        for line in page_lines:
            escaped = _escape_pdf_text(line)
            text_lines.append(f"({escaped}) Tj")
            text_lines.append(f"0 -{LINE_HEIGHT} Td")

        text_lines.append("ET")
        stream = "\n".join(text_lines).encode("latin-1")

        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
                f"{PAGE_WIDTH} {PAGE_HEIGHT}] "
                "/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("latin-1")
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )

    kids = " ".join(f"{object_id} 0 R" for object_id in page_object_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("latin-1")

    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")

    offsets = [0]
    for object_index, payload in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_index} 0 obj\n".encode("ascii"))
        pdf.extend(payload)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_start}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def generate_pdf(input_markdown: Path, output_pdf: Path) -> Path:
    """Generate the technical report PDF from markdown."""

    markdown_text = input_markdown.read_text(encoding="utf-8")
    lines = _markdown_to_lines(markdown_text)
    pages = _paginate(lines)
    pdf_bytes = _build_pdf_bytes(pages)
    output_pdf.write_bytes(pdf_bytes)
    return output_pdf


def main() -> None:
    project_root = Path(__file__).resolve().parent
    input_markdown = project_root / "FUSION_MODEL_TECHNICAL_REPORT.md"
    output_pdf = project_root / "artifacts" / "FUSION_MODEL_TECHNICAL_REPORT.pdf"
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    generated = generate_pdf(input_markdown, output_pdf)
    print(f"Generated PDF: {generated}")


if __name__ == "__main__":
    main()