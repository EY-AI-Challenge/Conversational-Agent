from __future__ import annotations

import argparse
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_CHUNK_WORDS = 500
DEFAULT_OVERLAP_WORDS = 60
DEFAULT_MIN_SCORE = 0.75
QUESTION_TERM_WEIGHT = 1.0
AREA_TERM_WEIGHT = 0.25
EXACT_QUERY_BONUS = 3.0

PAGE_MARKER_RE = re.compile(
    r"(?im)^\s*(?:={2,}|-{2,})?\s*(?:pagina|p[a\u00e1]gina|page)\s*(\d{1,4})\s*(?:={2,}|-{2,})?\s*$"
)
WORD_RE = re.compile(r"\b[\w\u00c0-\u00ff.-]+\b", re.UNICODE)

STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "daquilo",
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
    "tendencia",
    "um",
    "uma",
    "banco",
    "bdp",
    "boletim",
    "economico",
    "mensal",
    "portugal",
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
    ],
    "juros": [
        "juros",
        "taxas de juro",
        "euribor",
        "politica monetaria",
        "financiamento",
    ],
}


@dataclass(frozen=True)
class Chunk:
    id: int
    bulletin: str
    source_file: str
    page_start: int | None
    page_end: int | None
    text: str
    tokens: tuple[str, ...]

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def citation(self) -> str:
        if self.page_start is None:
            return self.bulletin
        if self.page_end is None or self.page_end == self.page_start:
            return f"{self.bulletin}, p. {self.page_start}"
        return f"{self.bulletin}, pp. {self.page_start}-{self.page_end}"


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_text(value: str) -> str:
    value = strip_accents(value.lower())
    value = value.replace("º", "").replace("ª", "")
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
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_pages(text: str) -> list[tuple[int | None, str]]:
    """Return page-numbered text blocks when the phase 1 extractor preserved pages."""
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


def load_chunks(
    data_dir: str | Path,
    *,
    pattern: str = "*.txt",
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[Chunk]:
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Directory not found: {data_path}")

    chunks: list[Chunk] = []
    next_id = 1
    for txt_file in sorted(data_path.glob(pattern)):
        raw_text = txt_file.read_text(encoding="utf-8", errors="ignore")
        bulletin = txt_file.stem

        for page_number, page_text in split_pages(raw_text):
            words = clean_extracted_text(page_text).split()
            for word_chunk in iter_word_chunks(
                words, chunk_words=chunk_words, overlap_words=overlap_words
            ):
                chunk_text = " ".join(word_chunk)
                chunks.append(
                    Chunk(
                        id=next_id,
                        bulletin=bulletin,
                        source_file=str(txt_file),
                        page_start=page_number,
                        page_end=page_number,
                        text=chunk_text,
                        tokens=tuple(tokenize(chunk_text)),
                    )
                )
                next_id += 1

    return chunks


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

    return f"""Es um assistente para consultores da EY a analisar Boletins Economicos Mensais do Banco de Portugal.
Usa exclusivamente o contexto fornecido. Se o contexto nao for suficiente, diz isso de forma clara e indica que informacao faltaria.

{area_line}Pergunta do consultor:
{question}

Contexto relevante:
{context}

Responde em portugues europeu com este formato:
1. Sumario executivo: duas linhas, direto e orientado para decisao.
2. Dados-chave: bullets curtos com numeros, tendencias ou sinais relevantes.
3. Implicacoes para BdP/EY: o que isto significa para supervisao, risco bancario ou aconselhamento ao cliente.
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
    parser = argparse.ArgumentParser(description="Phase 2 context builder for BdP bulletins.")
    parser.add_argument("--data-dir", default="Data/bdp_txt", help="Folder with phase 1 .txt files.")
    parser.add_argument("--pattern", default="*.txt", help="Text filename pattern.")
    parser.add_argument("--query", required=True, help="Consultant question or search theme.")
    parser.add_argument("--area", default=None, help="Optional area filter: inflacao, credito, energia, juros.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_MIN_SCORE,
        help="Minimum relevance score for a chunk to be included.",
    )
    parser.add_argument("--chunk-words", type=int, default=DEFAULT_CHUNK_WORDS)
    parser.add_argument("--overlap-words", type=int, default=DEFAULT_OVERLAP_WORDS)
    args = parser.parse_args()

    chunks = load_chunks(
        args.data_dir,
        pattern=args.pattern,
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
    print("\nTop matches:")
    print(preview_matches(scored) or "No matches found.")
    print("\nPrompt for LLM:")
    print(prompt)


if __name__ == "__main__":
    main()
