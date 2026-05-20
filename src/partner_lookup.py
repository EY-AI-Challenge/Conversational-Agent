import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Union

import pandas as pd


PARTNER_FILE_PATTERN = "*Partners*.xlsx"
SERVICE_COL = "Service Line/Sub-Service Line"
PARTNER_COL = "Partner\nResponsável"

QUESTION_TERMS = {
    "quem",
    "qual",
    "quais",
    "e",
    "o",
    "a",
    "os",
    "as",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "para",
    "sobre",
    "partner",
    "parceiro",
    "responsavel",
    "responsaveis",
    "lider",
    "lidera",
    "lead",
    "head",
}

PARTNER_INTENT_TERMS = {
    "partner",
    "parceiro",
    "responsavel",
    "responsaveis",
    "lider",
    "lidera",
    "lead",
    "head",
}


@dataclass(frozen=True)
class PartnerMatch:
    service_line: str
    partner: str
    source: str


def _normalize(text: object) -> str:
    text = str(text or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _query_terms(question: str) -> list[str]:
    return [
        term
        for term in _normalize(question).split()
        if term not in QUESTION_TERMS and len(term) > 1
    ]


def _display_query(terms: list[str]) -> str:
    special_terms = {"ai": "AI", "fso": "FSO", "and": "and"}
    return " ".join(special_terms.get(term, term.capitalize()) for term in terms)


class PartnerLookup:
    """Deterministic lookup for service-line partner ownership from Excel."""

    def __init__(self, data_dir: Union[Path, str] = "./Data"):
        self.data_dir = Path(data_dir)
        self.rows = self._load_rows()

    def _load_rows(self) -> list[PartnerMatch]:
        rows: list[PartnerMatch] = []
        for file_path in self.data_dir.glob(PARTNER_FILE_PATTERN):
            df = pd.read_excel(file_path)
            if SERVICE_COL not in df.columns or PARTNER_COL not in df.columns:
                continue

            for _, row in df.iterrows():
                service_line = row.get(SERVICE_COL)
                partner = row.get(PARTNER_COL)
                if pd.notna(service_line) and pd.notna(partner):
                    rows.append(
                        PartnerMatch(
                            service_line=str(service_line).strip(),
                            partner=str(partner).strip(),
                            source=file_path.name,
                        )
                    )
        return rows

    def answer(self, question: str) -> Optional[dict]:
        normalized_question = _normalize(question)
        if not any(term in normalized_question.split() for term in PARTNER_INTENT_TERMS):
            return None

        terms = _query_terms(question)
        if not terms:
            return None

        exact_token_matches = [
            row
            for row in self.rows
            if all(term in _normalize(row.service_line).split() for term in terms)
        ]
        if len(terms) == 1 and len(exact_token_matches) > 5:
            return None

        scored: list[tuple[float, PartnerMatch]] = []
        query = " ".join(terms)
        for row in self.rows:
            service = _normalize(row.service_line)
            contains_all_terms = all(term in service.split() for term in terms)
            contains_phrase = query in service
            similarity = SequenceMatcher(None, query, service).ratio()

            score = similarity
            if contains_phrase:
                score += 1.0
            if contains_all_terms:
                score += 0.75
            if terms and terms[-1] in service.split():
                score += 0.1

            if score >= 0.45:
                scored.append((score, row))

        if not scored:
            return None

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score = scored[0][0]
        matches = [row for score, row in scored if score >= best_score - 0.15]

        if len(matches) > 5:
            return None

        return {
            "answer": self._format_answer(matches, _display_query(terms)),
            "sources": list(dict.fromkeys(row.source for row in matches)),
        }

    def _format_answer(self, matches: list[PartnerMatch], query: str) -> str:
        if len(matches) == 1:
            match = matches[0]
            return (
                f"O partner responsável por **{match.service_line}** é "
                f"**{match.partner}**.\n\n"
                f"Fonte: `{match.source}`."
            )

        lines = [
            f"Encontrei mais do que uma entrada para **{query}** na base de dados:"
        ]
        for match in matches:
            lines.append(f"- **{match.service_line}**: **{match.partner}**")
        lines.append("")
        lines.append(f"Fonte: `{matches[0].source}`.")
        return "\n".join(lines)
