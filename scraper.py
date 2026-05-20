"""
BdP economic bulletin scraper.

Downloads the configured Banco de Portugal bulletins, extracts page-aware text,
and writes the files consumed by context.py and chatbot.py.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests


DATA_DIR = Path("bdp")
DELAY_SECS = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    "Referer": "https://www.bportugal.pt",
}

BOLETINS = [
    {
        "titulo": "Boletim Economico - marco 2026",
        "data": "2026-03",
        "url": "https://www.bportugal.pt/sites/default/files/documents/2026-03/Boletim%20Economico_mar%C3%A7o2026.pdf",
    },
    {
        "titulo": "Boletim Economico - outubro 2025",
        "data": "2025-10",
        "url": "https://www.bportugal.pt/sites/default/files/documents/2025-10/be_out2025.pdf",
    },
    {
        "titulo": "Boletim Economico - marco 2025",
        "data": "2025-03",
        "url": "https://www.bportugal.pt/sites/default/files/documents/2025-03/be_mar25.pdf",
    },
]


def download_pdf(url: str, dest: Path) -> bool:
    """Download one PDF unless it already exists."""
    if dest.exists():
        size_kb = dest.stat().st_size // 1024
        print(f"  already exists ({size_kb} KB): {dest.name}")
        return True

    try:
        print(f"  downloading {dest.name}...")
        response = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        response.raise_for_status()
        with dest.open("wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        size_kb = dest.stat().st_size // 1024
        print(f"  ok - {size_kb} KB saved")
        return True
    except requests.HTTPError as exc:
        print(f"  [HTTP error] {exc}")
        return False
    except Exception as exc:  # noqa: BLE001 - scraper should continue to the next bulletin.
        print(f"  [error] {exc}")
        return False


def extract_text(pdf_path: Path, txt_path: Path) -> str:
    """
    Extract text from a PDF with page markers that context.py can cite.
    """
    if txt_path.exists():
        print(f"  text already extracted: {txt_path.name}")
        return txt_path.read_text(encoding="utf-8", errors="ignore")

    pages_text: list[str] = []
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            print(f"  extracting text from {total} pages...", end="", flush=True)
            for index, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text and text.strip():
                    pages_text.append(f"[Page {index}]\n{text.strip()}")
                if index % 20 == 0:
                    print(f" {index}...", end="", flush=True)
            print(" done.")

        full_text = "\n\n".join(pages_text)
        txt_path.write_text(full_text, encoding="utf-8")
        print(f"  extracted {len(full_text.split()):,} words -> {txt_path.name}")
        return full_text
    except Exception as exc:  # noqa: BLE001 - scraper should report and keep going.
        print(f"\n  [extraction error] {exc}")
        return ""


def run(
    *,
    data_dir: str | Path = DATA_DIR,
    boletins: Iterable[dict[str, str]] = BOLETINS,
) -> list[dict[str, object]]:
    output_dir = Path(data_dir)
    output_dir.mkdir(exist_ok=True)
    bulletins = list(boletins)
    manifest: list[dict[str, object]] = []

    print("\nBdP economic bulletin scraper")
    print("=" * 50)
    print(f"Processing {len(bulletins)} bulletins into {output_dir}\n")

    for index, boletim in enumerate(bulletins, 1):
        print(f"[{index}/{len(bulletins)}] {boletim['titulo']}")

        slug = boletim["data"]
        pdf_path = output_dir / f"boletim_{index:02d}_{slug}.pdf"
        txt_path = output_dir / f"boletim_{index:02d}_{slug}.txt"

        entry: dict[str, object] = {
            "id": index,
            "titulo": boletim["titulo"],
            "data": boletim["data"],
            "url_pdf": boletim["url"],
            "ficheiro_pdf": str(pdf_path),
            "ficheiro_txt": None,
            "palavras": 0,
            "extraido_em": None,
        }

        if download_pdf(boletim["url"], pdf_path):
            text = extract_text(pdf_path, txt_path)
            if text:
                entry["ficheiro_txt"] = str(txt_path)
                entry["palavras"] = len(text.split())
                entry["extraido_em"] = datetime.now().isoformat()
        else:
            entry["erro"] = "download_failed"

        manifest.append(entry)
        print()

        if index < len(bulletins):
            time.sleep(DELAY_SECS)

    manifest_path = output_dir / "manifesto.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [item for item in manifest if item.get("ficheiro_txt")]
    print("=" * 50)
    print(f"Completed: {len(ok)}/{len(manifest)} bulletins with extracted text\n")
    for item in ok:
        print(f"  {str(item['titulo']):<40} {int(item['palavras']):>8,} words")
    print(f"\nManifest saved to: {manifest_path}")
    print("Next step: python chatbot.py")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and extract BdP economic bulletins.")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Output folder for PDFs, text, and manifesto.json.")
    args = parser.parse_args()
    run(data_dir=args.data_dir)


if __name__ == "__main__":
    main()
