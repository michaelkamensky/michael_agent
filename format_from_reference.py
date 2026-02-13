#!/usr/bin/python
import sys
from pathlib import Path
from typing import List, Tuple

import fitz  # PyMuPDF

PDF_ROOT = Path("/home/mike/projects/michael_agent/pdfs").resolve()
TEXT_ROOT = Path("/home/mike/projects/michael_agent/sources").resolve()
REF_ROOT = Path("/home/mike/projects/michael_agent/reference").resolve()


def _resolve_under(root: Path, path: str) -> Path:
    p = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if root not in p.parents and p != root:
        raise ValueError(f"Path must be under {root}")
    return p


def _extract_line_specs(ref_doc: fitz.Document) -> List[List[Tuple[fitz.Rect, str, float]]]:
    specs_by_page: List[List[Tuple[fitz.Rect, str, float]]] = []
    for page in ref_doc:
        text_dict = page.get_text("dict")
        lines: List[Tuple[fitz.Rect, str, float]] = []
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                if not line.get("spans"):
                    continue
                span = line["spans"][0]
                bbox = fitz.Rect(line["bbox"])
                font_name = span.get("font", "helv")
                font_size = float(span.get("size", 11))
                lines.append((bbox, font_name, font_size))
        # Preserve visual order top-to-bottom, left-to-right
        lines.sort(key=lambda item: (item[0].y0, item[0].x0))
        specs_by_page.append(lines)
    return specs_by_page


def _render_from_specs(
    specs_by_page: List[List[Tuple[fitz.Rect, str, float]]],
    ref_doc: fitz.Document,
    new_lines: List[str],
    out_path: Path,
) -> None:
    builtin_fonts = {"helv", "tiro", "cour", "symb", "zadb"}
    out_doc = fitz.open()

    # Create pages with same size as reference
    ref_pages = [p for p in ref_doc]
    for page_index, ref_page in enumerate(ref_pages):
        out_page = out_doc.new_page(width=ref_page.rect.width, height=ref_page.rect.height)
        page_specs = specs_by_page[page_index] if page_index < len(specs_by_page) else []
        for rect, font_name, font_size in page_specs:
            if not new_lines:
                break
            line = new_lines.pop(0).replace("\t", "    ")
            if not line.strip():
                continue
            use_font = font_name if font_name in builtin_fonts else "helv"
            out_page.insert_textbox(
                rect,
                line,
                fontname=use_font,
                fontsize=font_size,
                color=(0, 0, 0),
            )

    if new_lines:
        raise ValueError("Input text has more lines than the reference layout.")

    out_doc.save(str(out_path))
    out_doc.close()


def main() -> int:
    ref_default = "Michael Engineering Resume.pdf"
    source_path = input("Source text filename (under sources/): ").strip().strip("'\"")
    output_pdf = input("Output PDF filename (under pdfs/): ").strip().strip("'\"")
    ref_name = input(f"Reference PDF filename (default: {ref_default}): ").strip().strip("'\"") or ref_default

    text_path = _resolve_under(TEXT_ROOT, source_path)
    out_path = _resolve_under(PDF_ROOT, output_pdf)
    ref_path = _resolve_under(REF_ROOT, ref_name)

    if not text_path.is_file():
        raise FileNotFoundError(f"Source not found: {text_path}")
    if not ref_path.is_file():
        raise FileNotFoundError(f"Reference not found: {ref_path}")

    text = text_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    ref_doc = fitz.open(str(ref_path))
    specs_by_page = _extract_line_specs(ref_doc)
    if not specs_by_page or not any(specs_by_page):
        raise ValueError("Reference PDF has no readable text lines.")

    _render_from_specs(specs_by_page, ref_doc, lines, out_path)
    ref_doc.close()
    print(f"Wrote PDF to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
