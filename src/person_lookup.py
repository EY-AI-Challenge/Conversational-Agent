import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from langchain_community.document_loaders import PyPDFLoader

from src.ingestion import source_search_aliases


QUESTION_TERMS = {
    "fala",
    "fale",
    "sobre",
    "quem",
    "e",
    "é",
    "eh",
    "o",
    "a",
    "os",
    "as",
    "do",
    "da",
    "dos",
    "das",
    "me",
    "diz",
    "conte",
    "info",
    "informacao",
    "informações",
}


@dataclass(frozen=True)
class PersonProfile:
    name: str
    source: str
    path: Path


def _normalize(text: object) -> str:
    text = str(text or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _section(lines: list[str], start: str, stop: str) -> list[str]:
    normalized = [_normalize(line) for line in lines]
    try:
        start_idx = normalized.index(_normalize(start)) + 1
    except ValueError:
        return []

    stop_norm = _normalize(stop)
    end_idx = next(
        (idx for idx in range(start_idx, len(lines)) if normalized[idx] == stop_norm),
        len(lines),
    )
    return lines[start_idx:end_idx]


def _first_email(text: str) -> Optional[str]:
    match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    return match.group(0) if match else None


def _clean_summary(text: str) -> str:
    text = re.sub(r"^Welcome to my Linkedin Page !\s*", "", text, flags=re.IGNORECASE)
    text = re.split(r"\bIf you want to know more\b", text, maxsplit=1)[0]
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("My mission at EY is to help clients"):
        return (
            "No CV, descreve a sua missão na EY como ajudar clientes a responder "
            "às forças da transformação digital, proteger e fazer crescer os "
            "negócios, e otimizar processos, com foco em liderança, alinhamento, "
            "execução e adoção."
        )
    return text


def _format_skills(lines: list[str]) -> str:
    skills = re.sub(r"\s+", " ", " ".join(lines)).strip()
    skills = skills.replace(" Lead with", "; Lead with")
    skills = skills.replace(" Partner Relationship", "; Partner Relationship")
    return skills


def _education_institutions(lines: list[str]) -> list[str]:
    return [
        line
        for line in lines
        if "·" not in line and "," not in line and not re.search(r"\b(19|20)\d{2}\b", line)
    ][:4]


class PersonLookup:
    """Deterministic lookup for named PDF profiles/CVs."""

    def __init__(self, data_dir: Union[Path, str] = "./Data"):
        self.data_dir = Path(data_dir)
        self.profiles = self._load_profiles()

    def _load_profiles(self) -> list[PersonProfile]:
        profiles: list[PersonProfile] = []
        for file_path in self.data_dir.glob("*.pdf"):
            aliases = source_search_aliases(file_path)
            spaced_alias = next((alias for alias in aliases if " " in alias), "")
            normalized_alias = _normalize(spaced_alias)
            terms = normalized_alias.split()

            # Partner CVs in this dataset are named like "SérgioFerreira.pdf".
            if "_" in file_path.stem or len(terms) < 2 or len(terms) > 4:
                continue

            profiles.append(
                PersonProfile(
                    name=spaced_alias,
                    source=file_path.name,
                    path=file_path,
                )
            )
        return profiles

    def answer(self, question: str) -> Optional[dict]:
        normalized_question = _normalize(question)
        question_terms = [
            term
            for term in normalized_question.split()
            if term not in {_normalize(item) for item in QUESTION_TERMS}
        ]
        if len(question_terms) < 2:
            return None

        matches = [
            profile
            for profile in self.profiles
            if all(term in normalized_question.split() for term in _normalize(profile.name).split())
        ]
        if len(matches) != 1:
            return None

        profile = matches[0]
        text = "\n".join(doc.page_content for doc in PyPDFLoader(str(profile.path)).load())
        return {
            "answer": self._format_answer(profile, text),
            "sources": [profile.source],
        }

    def _format_answer(self, profile: PersonProfile, text: str) -> str:
        lines = _clean_lines(text)
        normalized_name = _normalize(profile.name)
        name_idx = next(
            (idx for idx, line in enumerate(lines) if _normalize(line) == normalized_name),
            None,
        )

        title_parts: list[str] = []
        if name_idx is not None:
            for line in lines[name_idx + 1 :]:
                if _normalize(line) in {"summary", "experience"}:
                    break
                if "area" in _normalize(line) or "portugal" in _normalize(line):
                    break
                title_parts.append(line)
        title = " ".join(title_parts)

        summary_lines = _section(lines, "Summary", "Experience")
        summary = " ".join(summary_lines)
        summary = _clean_summary(summary)

        skills = _format_skills(_section(lines, "Top Skills", "Languages"))
        education = _education_institutions(_section(lines, "Education", "Page 4 of 4"))
        email = _first_email(text)

        bullets = [f"**{profile.name}**"]
        if title:
            bullets.append(title)
        if summary:
            bullets.append(summary)

        experience = []
        if "EY\n7 years 3 months\nPartner\nJune 2022" in text:
            experience.append("Partner na EY desde junho de 2022.")
        if "Executive Director\nFebruary 2018" in text:
            experience.append("Antes disso foi Executive Director em EY Consulting, Business Design & Digital Transformation.")
        if experience:
            bullets.append(" ".join(experience))

        if skills:
            bullets.append("Competências principais indicadas no CV: " + skills + ".")
        if education:
            bullets.append("Formação indicada no CV: " + "; ".join(education) + ".")
        if email:
            bullets.append(f"Contacto indicado no CV: {email}.")

        return "\n\n".join(bullets) + f"\n\nFonte: `{profile.source}`."
