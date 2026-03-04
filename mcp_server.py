#!/usr/bin/python

from pathlib import Path
import shutil
import subprocess
import tempfile
import re
from typing import Optional
from urllib.request import Request, urlopen

import fitz  # PyMuPDF
from fastmcp import FastMCP
from fpdf import FPDF

from webscrapper.scraper import fetch_page_text

mcp = FastMCP("MathServer")
PDF_ROOT = Path("/home/mike/projects/michael_agent/pdfs").resolve()
TEXT_ROOT = Path("/home/mike/projects/michael_agent/sources").resolve()


def _resolve_pdf_path(path: str) -> Path:
    pdf_path = (PDF_ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if PDF_ROOT not in pdf_path.parents and pdf_path != PDF_ROOT:
        raise ValueError(f"Path must be under {PDF_ROOT}")
    return pdf_path


def _resolve_text_path(path: str) -> Path:
    text_path = (TEXT_ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if TEXT_ROOT not in text_path.parents and text_path != TEXT_ROOT:
        raise ValueError(f"Path must be under {TEXT_ROOT}")
    return text_path


def _sanitize_dir_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\s.-]", "", name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "company"


@mcp.tool()
def create_company_pdf_dir(company_name: str) -> str:
    """Create (or reuse) a company-named directory under the PDF root."""
    if not company_name or not company_name.strip():
        raise ValueError("company_name must be non-empty.")
    safe_name = _sanitize_dir_name(company_name)
    dir_path = _resolve_pdf_path(safe_name)
    dir_path.mkdir(parents=True, exist_ok=True)
    return f"PDF directory ready: {dir_path}"

@mcp.tool()
def multiply_numbers(a: int, b: int) -> int:
    """Multiplies two numbers together."""
    return a * b


@mcp.tool()
def read_pdf_text(path: str) -> str:
    """Extract text from a PDF file."""
    pdf_path = _resolve_pdf_path(path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages = []
    for page in doc:
        pages.append(page.get_text() or "")
    doc.close()
    return "\n".join(pages).strip()


@mcp.tool()
def read_text_source(path: str) -> str:
    """Read a text or markdown source file."""
    text_path = _resolve_text_path(path)
    if not text_path.is_file():
        raise FileNotFoundError(f"Source not found: {text_path}")
    return text_path.read_text(encoding="utf-8")


@mcp.tool()
def write_text_source(path: str, text: str) -> str:
    """Write a text or markdown source file (overwrites if it exists)."""
    text_path = _resolve_text_path(path)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")
    return f"Wrote source to {text_path}"


@mcp.tool()
def render_pdf_from_text(
    path: str,
    output_path: Optional[str] = None,
    font_name: str = "Helvetica",
    font_size: int = 12,
    line_height: int = 8,
) -> str:
    """Render a PDF from a text or markdown source file."""
    text_path = _resolve_text_path(path)
    if not text_path.is_file():
        raise FileNotFoundError(f"Source not found: {text_path}")

    out_path = _resolve_pdf_path(output_path) if output_path else _resolve_pdf_path(text_path.with_suffix(".pdf").name)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    text = text_path.read_text(encoding="utf-8")
    # Normalize common unicode punctuation for latin-1 PDF output.
    replacements = {
        "\u2014": "-",   # em dash
        "\u2013": "-",   # en dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2026": "...", # ellipsis
        "\u00a0": " ",   # non-breaking space
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    # Ensure remaining characters are latin-1 encodable
    text = text.encode("latin-1", errors="replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font(font_name, size=font_size)
    for line in text.splitlines():
        pdf.multi_cell(0, line_height, line)
    pdf.output(str(out_path))
    return f"Rendered PDF to {out_path}"


@mcp.tool()
def render_pdf_from_latex(
    path: str,
    output_path: Optional[str] = None,
) -> str:
    """Render a PDF from a LaTeX source file."""
    tex_path = _resolve_text_path(path)
    if not tex_path.is_file():
        raise FileNotFoundError(f"LaTeX source not found: {tex_path}")

    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        raise RuntimeError("pdflatex is required to render LaTeX. Install a TeX distribution (e.g., TeX Live).")

    out_path = _resolve_pdf_path(output_path) if output_path else _resolve_pdf_path(tex_path.with_suffix(".pdf").name)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            pdflatex,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={tmpdir}",
            tex_path.name,
        ]
        result = subprocess.run(
            cmd,
            cwd=str(tex_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            log = result.stdout.strip()
            raise RuntimeError(f"LaTeX render failed with exit code {result.returncode}.\n{log}")

        tmp_pdf = Path(tmpdir) / tex_path.with_suffix(".pdf").name
        if not tmp_pdf.is_file():
            raise RuntimeError("LaTeX render completed, but PDF output was not found.")

        shutil.copy2(tmp_pdf, out_path)

    return f"Rendered LaTeX PDF to {out_path}"


@mcp.tool()
def replace_text_in_pdf(
    path: str,
    find_text: str,
    replace_text: str,
    output_path: Optional[str] = None,
    max_replacements: Optional[int] = None,
) -> str:
    """
    Best-effort in-place text replacement preserving layout and fonts where possible.
    Uses redaction + re-insertion; not all PDFs are fully editable.
    """
    if not find_text:
        raise ValueError("find_text must be non-empty.")

    pdf_path = _resolve_pdf_path(path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    out_path = _resolve_pdf_path(output_path) if output_path else pdf_path

    doc = fitz.open(str(pdf_path))
    total_replaced = 0

    builtin_fonts = {"helv", "tiro", "cour", "symb", "zadb"}

    for page in doc:
        if max_replacements is not None and total_replaced >= max_replacements:
            break

        matches = page.search_for(find_text)
        if not matches:
            continue

        text_dict = page.get_text("dict")
        spans = []
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    spans.append(span)

        for rect in matches:
            if max_replacements is not None and total_replaced >= max_replacements:
                break

            # Find a span overlapping the match to reuse font info when possible.
            font_name = "helv"
            font_size = 11
            for span in spans:
                bbox = fitz.Rect(span["bbox"])
                if rect.intersects(bbox):
                    font_name = span.get("font", "helv")
                    font_size = span.get("size", 11)
                    break

            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
            use_font_name = font_name if font_name in builtin_fonts else "helv"
            # insert_textbox returns 0 if text didn't fit; try smaller fonts.
            inserted = 0.0
            for size in range(int(font_size), 3, -1):
                inserted = page.insert_textbox(
                    rect,
                    replace_text,
                    fontname=use_font_name,
                    fontsize=float(size),
                    color=(0, 0, 0),
                )
                if inserted > 0:
                    break
            if inserted == 0:
                # Fallback: place at top-left of the rect without box fitting.
                page.insert_text(
                    rect.tl,
                    replace_text,
                    fontname=use_font_name,
                    fontsize=float(font_size),
                    color=(0, 0, 0),
                )
            total_replaced += 1

    doc.save(str(out_path))
    doc.close()
    return f"Replaced {total_replaced} occurrence(s) in {out_path}"


@mcp.tool()
def scrape_url_text(url: str) -> dict:
    """Fetch a URL and return extracted text in a JSON-compatible dict."""
    return fetch_page_text(url)


@mcp.tool()
def fetch_html(url: str, user_agent: str = "Mozilla/5.0") -> dict:
    """Fetch raw HTML for a URL."""
    req = Request(url, headers={"User-Agent": user_agent})
    with urlopen(req) as resp:
        html = resp.read().decode("utf-8", errors="replace")
        return {"url": url, "status": getattr(resp, "status", None), "html": html}


def _require_playwright_async():
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Playwright is required for this tool. Install with: pip install playwright && playwright install"
        ) from exc
    return async_playwright


@mcp.tool()
async def fetch_dom_text(
    url: str,
    wait_for: Optional[str] = None,
    timeout_ms: int = 30000,
    wait_after_ms: int = 0,
) -> dict:
    """Fetch rendered DOM HTML and visible text using a headless browser."""
    async_playwright = _require_playwright_async()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)
        if wait_after_ms:
            await page.wait_for_timeout(wait_after_ms)
        html = await page.content()
        text = await page.inner_text("body")
        await browser.close()
    return {"url": url, "html": html, "text": text}


@mcp.tool()
async def fetch_accessibility_tree(url: str, wait_for: Optional[str] = None, timeout_ms: int = 30000) -> dict:
    """Fetch the accessibility tree snapshot for a page."""
    async_playwright = _require_playwright_async()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)
        snapshot = await page.accessibility.snapshot()
        await browser.close()
    return {"url": url, "accessibility_tree": snapshot}


@mcp.tool()
async def click_and_extract(
    url: str,
    selector: str,
    wait_for: Optional[str] = None,
    timeout_ms: int = 30000,
    wait_after_ms: int = 500,
) -> dict:
    """Click a selector and return updated DOM HTML and visible text."""
    async_playwright = _require_playwright_async()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)
        await page.click(selector, timeout=timeout_ms)
        if wait_after_ms:
            await page.wait_for_timeout(wait_after_ms)
        html = await page.content()
        text = await page.inner_text("body")
        await browser.close()
    return {"url": url, "selector": selector, "html": html, "text": text}


if __name__ == "__main__":
    # Start the server on a specific port using HTTP transport
    mcp.run(transport="http", host="0.0.0.0", port=8000)
