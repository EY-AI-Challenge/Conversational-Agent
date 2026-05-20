"""
BdP Boletins Económicos — Scraper (Fase 1)
==========================================
Descarrega os últimos 3 Boletins Económicos do BdP e extrai o texto.

Setup:
    python -m venv venv
    source venv/bin/activate        # Windows: venv\Scripts\activate
    pip install -r requirements.txt

Uso:
    python scraper.py
"""

import requests
import pdfplumber
import json
import time
from pathlib import Path
from datetime import datetime

# ── Configuração ──────────────────────────────────────────────────

DATA_DIR   = Path("bdp")
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

# ── URLs dos 3 boletins mais recentes ────────────────────────────
# Padrão BdP: /sites/default/files/documents/AAAA-MM/be_MMMAAAA.pdf
# Atualiza aqui quando saírem novos boletins.

BOLETINS = [
    {
        "titulo": "Boletim Económico — março 2026",
        "data": "2026-03",
        "url": "https://www.bportugal.pt/sites/default/files/documents/2026-03/Boletim%20Economico_mar%C3%A7o2026.pdf",
    },
    {
        "titulo": "Boletim Económico — outubro 2025",
        "data": "2025-10",
        "url": "https://www.bportugal.pt/sites/default/files/documents/2025-10/be_out2025.pdf",
    },
    {
        "titulo": "Boletim Económico — março 2025",
        "data": "2025-03",
        "url": "https://www.bportugal.pt/sites/default/files/documents/2025-03/be_mar25.pdf",
    },
]

# ── Funções ───────────────────────────────────────────────────────

def download_pdf(url: str, dest: Path) -> bool:
    """Faz download de um PDF para dest. Devolve True se OK."""
    if dest.exists():
        size_kb = dest.stat().st_size // 1024
        print(f"  (já existe, {size_kb} KB) {dest.name}")
        return True
    try:
        print(f"  A descarregar {dest.name}...")
        r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = dest.stat().st_size // 1024
        print(f"  OK — {size_kb} KB guardados")
        return True
    except requests.HTTPError as e:
        print(f"  [ERRO HTTP] {e}")
        return False
    except Exception as e:
        print(f"  [ERRO] {e}")
        return False


def extract_text(pdf_path: Path, txt_path: Path) -> str:
    """
    Extrai texto de um PDF com pdfplumber.
    Guarda em .txt e devolve o texto completo.
    Cada página é separada com o seu número — útil para citar fontes.
    """
    if txt_path.exists():
        print(f"  (texto já extraído) {txt_path.name}")
        return txt_path.read_text(encoding="utf-8")

    pages_text = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            print(f"  A extrair texto de {total} páginas...", end="", flush=True)
            for i, page in enumerate(pdf.pages, 1):
                t = page.extract_text()
                if t and t.strip():
                    pages_text.append(f"[Página {i}]\n{t.strip()}")
                if i % 20 == 0:
                    print(f" {i}...", end="", flush=True)
            print(" pronto.")

        full_text = "\n\n".join(pages_text)
        txt_path.write_text(full_text, encoding="utf-8")
        words = len(full_text.split())
        chars = len(full_text)
        print(f"  Extraído: {words:,} palavras / {chars:,} caracteres → {txt_path.name}")
        return full_text

    except Exception as e:
        print(f"\n  [ERRO extração] {e}")
        return ""


def run():
    DATA_DIR.mkdir(exist_ok=True)
    manifest = []

    print("\nBdP Boletins Económicos — Scraper Fase 1")
    print("=" * 50)
    print(f"A processar {len(BOLETINS)} boletins...\n")

    for i, boletim in enumerate(BOLETINS, 1):
        print(f"[{i}/{len(BOLETINS)}] {boletim['titulo']}")

        # Nome do ficheiro: boletim_01_2026-03.pdf
        slug = boletim["data"]
        pdf_path = DATA_DIR / f"boletim_{i:02d}_{slug}.pdf"
        txt_path = DATA_DIR / f"boletim_{i:02d}_{slug}.txt"

        entry = {
            "id": i,
            "titulo": boletim["titulo"],
            "data": boletim["data"],
            "url_pdf": boletim["url"],
            "ficheiro_pdf": str(pdf_path),
            "ficheiro_txt": None,
            "palavras": 0,
            "extraido_em": None,
        }

        # Download
        if download_pdf(boletim["url"], pdf_path):
            # Extração de texto
            text = extract_text(pdf_path, txt_path)
            if text:
                entry["ficheiro_txt"] = str(txt_path)
                entry["palavras"] = len(text.split())
                entry["extraido_em"] = datetime.now().isoformat()
        else:
            entry["erro"] = "download_falhou"

        manifest.append(entry)
        print()

        if i < len(BOLETINS):
            time.sleep(DELAY_SECS)

    # Manifesto JSON
    manifest_path = DATA_DIR / "manifesto.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Resumo final
    print("=" * 50)
    ok = [m for m in manifest if m.get("ficheiro_txt")]
    print(f"Concluído: {len(ok)}/{len(manifest)} boletins com texto extraído\n")
    for m in ok:
        print(f"  {m['titulo']:<45} {m['palavras']:>8,} palavras")
    print(f"\nManifesto guardado em: {manifest_path}")
    print("\nPróximo passo: python parser.py")


if __name__ == "__main__":
    run()