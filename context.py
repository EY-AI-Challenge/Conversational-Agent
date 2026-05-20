from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PROJECT_DATA_DIRS = (PROJECT_ROOT / "bdp", PROJECT_ROOT / "Data")
DEFAULT_CACHE_DIR = PROJECT_ROOT / ".cache" / "context_text"
DEFAULT_CHUNK_WORDS = 450
DEFAULT_OVERLAP_WORDS = 70
DEFAULT_MIN_SCORE = 0.35
QUESTION_TERM_WEIGHT = 1.0
AREA_TERM_WEIGHT = 0.25
EXACT_QUERY_BONUS = 3.0
_MISSING_PDFPLUMBER_WARNED = False

PAGE_MARKER_RE = re.compile(
    r"(?im)^\s*(?:\[|\(|={2,}|-{2,})?\s*"
    r"(?:pagina|p[a\u00e1]gina|page)\s*(\d{1,4})"
    r"\s*(?:\]|\)|={2,}|-{2,})?\s*$"
)
WORD_RE = re.compile(r"\b[\w\u00c0-\u00ff.-]+\b", re.UNICODE)

STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "entre",
    "esta",
    "estao",
    "foi",
    "ha",
    "informacao",
    "informacoes",
    "existe",
    "existem",
    "explica",
    "explicar",
    "me",
    "diz",
    "da",
    "dar",
    "quero",
    "queria",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "qual",
    "quais",
    "que",
    "se",
    "sem",
    "sobre",
    "um",
    "uma",
    "the",
    "and",
    "for",
    "from",
    "with",
    "that",
    "this",
    "what",
    "which",
    "about",
    "information",
    "into",
    "our",
    "can",
    "are",
    "was",
    "were",
    "has",
    "have",
}

AREA_TERMS = {
    "inflacao": [
        "inflacao",
        "precos",
        "ipc",
        "ihpc",
        "energia",
        "bens alimentares",
        "pressao inflacionista",
    ],
    "credito": [
        "credito",
        "emprestimos",
        "endividamento",
        "empresas",
        "pme",
        "familias",
        "bancos",
    ],
    "energia": [
        "energia",
        "eletricidade",
        "gas",
        "petroleo",
        "combustiveis",
        "transicao energetica",
        "analytics4vegetation",
        "natural gas",
    ],
    "juros": [
        "juros",
        "taxas de juro",
        "euribor",
        "politica monetaria",
        "financiamento",
    ],
    "ey": [
        "ey",
        "consulting",
        "assurance",
        "tax",
        "strategy",
        "transactions",
        "partners",
        "carreiras",
        "servicos",
    ],
    "risco": [
        "risco",
        "fraude",
        "fraud",
        "compliance",
        "risk",
        "machine learning",
        "indicadores",
    ],
    "ia": [
        "ia",
        "ai",
        "inteligencia artificial",
        "analytics",
        "machine learning",
        "automacao",
    ],
}


@dataclass(frozen=True)
class Chunk:
    id: int
    source_name: str
    source_file: str
    text: str
    tokens: tuple[str, ...]
    source_kind: str = "document"
    page_start: int | None = None
    page_end: int | None = None

    @property
    def bulletin(self) -> str:
        return self.source_name

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def citation(self) -> str:
        if self.page_start is None:
            return self.source_name
        if self.page_end is None or self.page_end == self.page_start:
            return f"{self.source_name}, p. {self.page_start}"
        return f"{self.source_name}, pp. {self.page_start}-{self.page_end}"


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _mojibake_score(value: str) -> int:
    markers = ("Ã", "Â", "â", "ï")
    return sum(value.count(marker) for marker in markers)


def repair_mojibake(value: str) -> str:
    """Fix the common UTF-8-as-Windows-1252 artefacts present in the dataset."""
    if not value or _mojibake_score(value) == 0:
        return value

    best = value
    best_score = _mojibake_score(value)
    for encoding in ("cp1252", "latin1"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue

        score = _mojibake_score(candidate)
        if score < best_score:
            best = candidate
            best_score = score

    return best


def normalize_text(value: str) -> str:
    value = repair_mojibake(value)
    value = strip_accents(value.lower())
    value = value.replace("º", "").replace("ª", "")
    value = value.replace("Âº", "").replace("Âª", "")
    return re.sub(r"\s+", " ", value).strip()


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens = []
    for match in WORD_RE.finditer(normalized):
        token = match.group(0).strip(".-")
        if len(token) > 1 and token not in STOPWORDS:
            tokens.append(token)
    return tokens


def clean_extracted_text(text: str) -> str:
    text = repair_mojibake(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_pages(text: str) -> list[tuple[int | None, str]]:
    text = clean_extracted_text(text)
    if "\f" in text:
        pages = []
        for index, page_text in enumerate(text.split("\f"), start=1):
            page_text = clean_extracted_text(page_text)
            if page_text:
                pages.append((index, page_text))
        return pages

    matches = list(PAGE_MARKER_RE.finditer(text))
    if not matches:
        return [(None, text)] if text else []

    pages: list[tuple[int | None, str]] = []
    prefix = clean_extracted_text(text[: matches[0].start()])
    if prefix:
        pages.append((None, prefix))

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page_text = clean_extracted_text(text[start:end])
        if page_text:
            pages.append((int(match.group(1)), page_text))

    return pages


def iter_word_chunks(
    words: list[str],
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> Iterable[list[str]]:
    if chunk_words <= 0:
        raise ValueError("chunk_words must be greater than zero")
    if overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("overlap_words must be between 0 and chunk_words - 1")

    step = chunk_words - overlap_words
    for start in range(0, len(words), step):
        chunk = words[start : start + chunk_words]
        if chunk:
            yield chunk
        if start + chunk_words >= len(words):
            break


def _path_list(paths: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    return [Path(path) for path in paths]


def _cache_path_for(source_path: Path, cache_dir: Path) -> Path:
    stat = source_path.stat()
    fingerprint = f"{source_path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.txt"


def _format_pages(pages: list[tuple[int | None, str]]) -> str:
    blocks = []
    for page_number, page_text in pages:
        if page_number is None:
            blocks.append(clean_extracted_text(page_text))
        else:
            blocks.append(f"[Page {page_number}]\n{clean_extracted_text(page_text)}")
    return "\n\n".join(block for block in blocks if block)


def _load_pdf_pages(pdf_path: Path, cache_dir: Path | None = DEFAULT_CACHE_DIR) -> list[tuple[int | None, str]]:
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_path = _cache_path_for(pdf_path, cache_dir)
        if cached_path.exists():
            return split_pages(cached_path.read_text(encoding="utf-8", errors="ignore"))

    global _MISSING_PDFPLUMBER_WARNED
    try:
        import pdfplumber
    except ImportError as exc:
        if not _MISSING_PDFPLUMBER_WARNED:
            print(
                "Warning: pdfplumber is not installed, so PDF files are being skipped. "
                "The chatbot will still use existing .txt and .xlsx context.",
                file=sys.stderr,
            )
            _MISSING_PDFPLUMBER_WARNED = True
        return []

    pages: list[tuple[int | None, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            page_text = clean_extracted_text(page_text)
            if page_text:
                pages.append((index, page_text))

    if cache_dir is not None and pages:
        cached_path.write_text(_format_pages(pages), encoding="utf-8")

    return pages


def _xml_text(element: ET.Element) -> str:
    return "".join(text_node.text or "" for text_node in element.iter() if text_node.tag.endswith("}t"))


def _load_xlsx_pages(xlsx_path: Path) -> list[tuple[int | None, str]]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    lines: list[str] = []

    with zipfile.ZipFile(xlsx_path) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in root.findall("main:si", ns):
                shared_strings.append(_xml_text(item))

        sheet_paths = sorted(
            name
            for name in workbook.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        for sheet_path in sheet_paths:
            lines.append(f"Worksheet: {Path(sheet_path).stem}")
            sheet = ET.fromstring(workbook.read(sheet_path))
            for row in sheet.findall(".//main:row", ns):
                values: list[str] = []
                for cell in row.findall("main:c", ns):
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find("main:v", ns)
                    inline_node = cell.find("main:is", ns)
                    value = ""
                    if cell_type == "s" and value_node is not None:
                        index = int(value_node.text or "0")
                        value = shared_strings[index] if index < len(shared_strings) else ""
                    elif cell_type == "inlineStr" and inline_node is not None:
                        value = _xml_text(inline_node)
                    elif value_node is not None:
                        value = value_node.text or ""
                    if value:
                        values.append(clean_extracted_text(value))
                if values:
                    lines.append(" | ".join(values))

    text = "\n".join(lines)
    return [(None, text)] if text.strip() else []


def _load_text_pages(txt_path: Path) -> list[tuple[int | None, str]]:
    return split_pages(txt_path.read_text(encoding="utf-8", errors="ignore"))


def _source_kind(path: Path) -> str:
    normalized_parts = {normalize_text(part) for part in path.parts}
    if path.suffix.lower() == ".xlsx":
        return "spreadsheet"
    if "bdp" in normalized_parts:
        return "bdp"
    if "data" in normalized_parts:
        return "ey"
    return path.suffix.lower().lstrip(".") or "document"


def _manifest_titles(roots: Sequence[Path]) -> dict[Path, str]:
    titles: dict[Path, str] = {}
    for root in roots:
        manifest_paths = [root] if root.is_file() and root.name == "manifesto.json" else []
        if root.is_dir():
            manifest_paths.extend(root.glob("manifesto.json"))

        for manifest_path in manifest_paths:
            try:
                raw = manifest_path.read_text(encoding="utf-8", errors="ignore")
                entries = json.loads(repair_mojibake(raw))
            except (OSError, json.JSONDecodeError):
                continue

            if not isinstance(entries, list):
                continue

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                title = clean_extracted_text(str(entry.get("titulo") or ""))
                if not title:
                    continue
                for key in ("ficheiro_txt", "ficheiro_pdf"):
                    value = entry.get(key)
                    if not value:
                        continue
                    relative = Path(str(value))
                    candidates = [
                        PROJECT_ROOT / relative,
                        manifest_path.parent / relative.name,
                        manifest_path.parent / relative,
                    ]
                    for candidate in candidates:
                        if candidate.exists():
                            titles[candidate.resolve()] = title
    return titles


def _source_name(path: Path, titles_by_path: dict[Path, str]) -> str:
    title = titles_by_path.get(path.resolve())
    if title:
        return title
    return clean_extracted_text(path.stem.replace("_", " "))


def _collect_files(
    roots: Sequence[Path],
    *,
    extensions: Sequence[str],
) -> list[Path]:
    wanted = {extension.lower() for extension in extensions}
    ignored_parts = {".git", ".cache", "__pycache__", "venv", ".venv"}
    files: list[Path] = []

    for root in roots:
        if root.is_file():
            if root.suffix.lower() in wanted:
                files.append(root)
            continue

        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in wanted:
                continue
            if ignored_parts.intersection(path.parts):
                continue
            files.append(path)

    return sorted(set(files), key=lambda item: str(item).lower())


def _pages_for_file(path: Path, cache_dir: Path | None = DEFAULT_CACHE_DIR) -> list[tuple[int | None, str]]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _load_text_pages(path)
    if suffix == ".pdf":
        return _load_pdf_pages(path, cache_dir=cache_dir)
    if suffix == ".xlsx":
        return _load_xlsx_pages(path)
    return []


def _chunks_from_files(
    files: Sequence[Path],
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
    cache_dir: Path | None = DEFAULT_CACHE_DIR,
    titles_by_path: dict[Path, str] | None = None,
) -> list[Chunk]:
    titles_by_path = titles_by_path or {}
    chunks: list[Chunk] = []
    next_id = 1

    for source_path in files:
        pages = _pages_for_file(source_path, cache_dir=cache_dir)
        source_name = _source_name(source_path, titles_by_path)
        source_kind = _source_kind(source_path)

        for page_number, page_text in pages:
            words = clean_extracted_text(page_text).split()
            for word_chunk in iter_word_chunks(
                words,
                chunk_words=chunk_words,
                overlap_words=overlap_words,
            ):
                chunk_text = " ".join(word_chunk)
                chunks.append(
                    Chunk(
                        id=next_id,
                        source_name=source_name,
                        source_file=str(source_path),
                        text=chunk_text,
                        tokens=tuple(tokenize(chunk_text)),
                        source_kind=source_kind,
                        page_start=page_number,
                        page_end=page_number,
                    )
                )
                next_id += 1

    return chunks


def load_chunks(
    data_dir: str | Path | Sequence[str | Path],
    *,
    pattern: str = "*.txt",
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[Chunk]:
    """Backward-compatible loader for text files used by the original phase 2 script."""
    roots = _path_list(data_dir)
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.match(pattern):
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.glob(pattern)))

    titles = _manifest_titles(roots)
    return _chunks_from_files(
        files,
        chunk_words=chunk_words,
        overlap_words=overlap_words,
        cache_dir=None,
        titles_by_path=titles,
    )


def load_project_chunks(
    data_dirs: Sequence[str | Path] | None = None,
    *,
    include_pdfs: bool = True,
    include_spreadsheets: bool = True,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
    cache_dir: Path | None = DEFAULT_CACHE_DIR,
) -> list[Chunk]:
    roots = [Path(path) for path in (data_dirs or DEFAULT_PROJECT_DATA_DIRS)]
    extensions = [".txt"]
    if include_pdfs:
        extensions.append(".pdf")
    if include_spreadsheets:
        extensions.append(".xlsx")

    files = _collect_files(roots, extensions=extensions)
    titles = _manifest_titles(roots)
    return _chunks_from_files(
        files,
        chunk_words=chunk_words,
        overlap_words=overlap_words,
        cache_dir=cache_dir,
        titles_by_path=titles,
    )


def source_summary(chunks: Sequence[Chunk]) -> list[dict[str, object]]:
    by_source: dict[str, dict[str, object]] = {}
    for chunk in chunks:
        item = by_source.setdefault(
            chunk.source_file,
            {
                "source_name": chunk.source_name,
                "source_file": chunk.source_file,
                "source_kind": chunk.source_kind,
                "chunks": 0,
                "words": 0,
            },
        )
        item["chunks"] = int(item["chunks"]) + 1
        item["words"] = int(item["words"]) + chunk.word_count
    return sorted(by_source.values(), key=lambda item: str(item["source_name"]).lower())


def _idf_by_term(chunks: list[Chunk]) -> dict[str, float]:
    document_count = len(chunks)
    document_frequency: Counter[str] = Counter()
    for chunk in chunks:
        document_frequency.update(set(chunk.tokens))

    return {
        term: math.log((1 + document_count) / (1 + frequency)) + 1
        for term, frequency in document_frequency.items()
    }


def _area_key(area: str | None) -> str | None:
    if not area:
        return None
    return normalize_text(area).replace(" ", "_")


def _filter_by_area(chunks: list[Chunk], area: str | None) -> list[Chunk]:
    key = _area_key(area)
    if not key:
        return chunks

    area_terms = AREA_TERMS.get(key, [area or ""])
    area_tokens = set(tokenize(" ".join(area_terms)))
    filtered = [chunk for chunk in chunks if area_tokens.intersection(chunk.tokens)]

    return filtered or chunks


def _weighted_search_terms(query: str, area: str | None) -> tuple[dict[str, float], set[str]]:
    weights: dict[str, float] = {}
    question_tokens = tokenize(query)
    primary_tokens = set(question_tokens)

    for token in question_tokens:
        weights[token] = weights.get(token, 0.0) + QUESTION_TERM_WEIGHT

    area_terms = AREA_TERMS.get(_area_key(area) or "", [])
    for token in tokenize(" ".join(area_terms)):
        weights[token] = weights.get(token, 0.0) + AREA_TERM_WEIGHT

    return weights, primary_tokens


def score_chunks(
    query: str,
    chunks: list[Chunk],
    *,
    area: str | None = None,
    min_score: float = 0.0,
) -> list[tuple[Chunk, float]]:
    candidates = _filter_by_area(chunks, area)
    if not candidates:
        return []

    weighted_terms, primary_tokens = _weighted_search_terms(query, area)
    if not weighted_terms:
        return []

    idf = _idf_by_term(candidates)
    scored: list[tuple[Chunk, float]] = []
    normalized_query = normalize_text(query)

    for chunk in candidates:
        chunk_counter = Counter(chunk.tokens)
        chunk_tokens = set(chunk.tokens)
        primary_hits = primary_tokens.intersection(chunk_tokens)

        if primary_tokens and not primary_hits:
            continue

        raw_score = 0.0
        for term, query_weight in weighted_terms.items():
            if term in chunk_counter:
                raw_score += (1 + math.log(chunk_counter[term])) * idf.get(term, 1.0) * query_weight

        normalized_chunk = normalize_text(chunk.text)
        if normalized_query and normalized_query in normalized_chunk:
            raw_score += EXACT_QUERY_BONUS

        if raw_score > 0:
            length_penalty = 1 + math.log(max(len(chunk.tokens), 2))
            score = raw_score / length_penalty
            if score >= min_score:
                scored.append((chunk, score))

    return sorted(scored, key=lambda item: item[1], reverse=True)


def search_chunks(
    query: str,
    chunks: list[Chunk],
    *,
    top_k: int = 5,
    area: str | None = None,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[Chunk]:
    scored = score_chunks(query, chunks, area=area, min_score=min_score)
    return [chunk for chunk, _score in scored[:top_k]]


def build_consultant_prompt(
    question: str,
    relevant_chunks: list[Chunk],
    *,
    area: str | None = None,
) -> str:
    context_blocks = []
    for index, chunk in enumerate(relevant_chunks, start=1):
        context_blocks.append(f"[Fonte {index}: {chunk.citation}]\n{chunk.text}")

    context = "\n\n".join(context_blocks) if context_blocks else "Sem contexto encontrado."
    area_line = f"Area de analise: {area}\n" if area else ""

    return f"""Es um assistente de conhecimento para profissionais da EY em Portugal.
Tens acesso a contexto interno EY e a fontes externas recolhidas por scraping, incluindo boletins economicos do Banco de Portugal.
Usa exclusivamente o contexto fornecido. Se o contexto nao for suficiente, diz isso de forma clara e indica que informacao faltaria.

{area_line}Pergunta do consultor:
{question}

Contexto relevante:
{context}

Responde em portugues europeu com este formato:
1. Sumario executivo: duas linhas, direto e orientado para decisao.
2. Dados-chave: bullets curtos com numeros, tendencias, pessoas, equipas ou sinais relevantes.
3. Implicacoes para EY: o que isto significa para aconselhamento ao cliente, operacoes internas ou risco.
4. Fontes: cita as fontes usadas no formato [Fonte X].
"""


def preview_matches(scored: list[tuple[Chunk, float]]) -> str:
    lines = []
    for chunk, score in scored:
        snippet = chunk.text[:260].replace("\n", " ")
        if len(chunk.text) > 260:
            snippet += "..."
        lines.append(f"- score={score:.3f} | {chunk.citation} | {snippet}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Context builder for the EY chatbot.")
    parser.add_argument(
        "--data-dir",
        action="append",
        default=None,
        help="Folder or file to index. Can be passed more than once. Defaults to bdp/ and Data/.",
    )
    parser.add_argument("--pattern", default=None, help="Optional text glob for the legacy txt-only loader.")
    parser.add_argument("--query", required=True, help="Consultant question or search theme.")
    parser.add_argument("--area", default=None, help="Optional area filter, e.g. inflacao, credito, energia, ey, risco.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_MIN_SCORE,
        help="Minimum relevance score for a chunk to be included.",
    )
    parser.add_argument("--chunk-words", type=int, default=DEFAULT_CHUNK_WORDS)
    parser.add_argument("--overlap-words", type=int, default=DEFAULT_OVERLAP_WORDS)
    parser.add_argument("--no-pdfs", action="store_true", help="Skip PDF indexing.")
    parser.add_argument("--no-spreadsheets", action="store_true", help="Skip XLSX indexing.")
    args = parser.parse_args()

    data_dirs = args.data_dir or [str(path) for path in DEFAULT_PROJECT_DATA_DIRS]
    if args.pattern:
        chunks = load_chunks(
            data_dirs,
            pattern=args.pattern,
            chunk_words=args.chunk_words,
            overlap_words=args.overlap_words,
        )
    else:
        chunks = load_project_chunks(
            data_dirs,
            include_pdfs=not args.no_pdfs,
            include_spreadsheets=not args.no_spreadsheets,
            chunk_words=args.chunk_words,
            overlap_words=args.overlap_words,
        )

    scored = score_chunks(
        args.query,
        chunks,
        area=args.area,
        min_score=args.min_score,
    )[: args.top_k]
    prompt = build_consultant_prompt(
        args.query,
        [chunk for chunk, _score in scored],
        area=args.area,
    )

    print(f"Loaded chunks: {len(chunks)}")
    print(f"Loaded sources: {len(source_summary(chunks))}")
    print("\nTop matches:")
    print(preview_matches(scored) or "No matches found.")
    print("\nPrompt for LLM:")
    print(prompt)


if __name__ == "__main__":
    main()
