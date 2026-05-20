from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from context import (
    DEFAULT_MIN_SCORE,
    DEFAULT_PROJECT_DATA_DIRS,
    Chunk,
    build_consultant_prompt,
    load_project_chunks,
    score_chunks,
    source_summary,
    tokenize,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
GREETING_TOKENS = {
    "ola",
    "oi",
    "hello",
    "hi",
    "bom",
    "boa",
    "dia",
    "tarde",
    "noite",
}
DOMAIN_TERMS = {
    "bdp",
    "banco",
    "portugal",
    "boletim",
    "economico",
    "economia",
    "macroeconomia",
    "inflacao",
    "credito",
    "juros",
    "euribor",
    "empresas",
    "pme",
    "risco",
    "fraude",
    "fraud",
    "fraudradar",
    "energia",
    "ey",
    "partner",
    "partners",
    "equipa",
    "consulting",
    "assurance",
    "tax",
    "strategy",
    "transactions",
    "service",
    "servicos",
    "ia",
    "ai",
    "inteligencia",
    "analytics",
}
EY_INTENT_TERMS = {
    "ey",
    "equipa",
    "equipas",
    "partner",
    "partners",
    "solucao",
    "solucoes",
    "servico",
    "servicos",
    "capacidades",
}
NOISY_EXTRACT_MARKERS = {
    "ocimónoc",
    "ocimonom",
    "mitelob",
    "lagutrop",
    "ocnab",
    "oçram",
    "painel a",
    "painel b",
}
NO_CONTEXT_ANSWER = (
    "1. Sumario executivo: Nao encontrei contexto suficiente na base de conhecimento carregada para responder com seguranca.\n"
    "2. Dados-chave:\n"
    "- Tenta reformular a pergunta com uma fonte, area, pessoa, servico, risco ou tema economico especifico.\n"
    "3. Implicacoes para EY: A resposta deve ficar limitada ao conhecimento EY/BdP disponivel no prototipo.\n"
    "4. Fontes: Sem fontes relevantes."
)
OUT_OF_SCOPE_ANSWER = (
    "1. Sumario executivo: Esta pergunta parece estar fora do ambito do Smart Supervision.\n"
    "2. Dados-chave:\n"
    "- Posso ajudar com boletins BdP, riscos para empresas, inflacao, credito, energia, FraudRadar, equipas EY e informacao interna carregada.\n"
    "3. Implicacoes para EY: Para a demo, usa perguntas ligadas a decisao empresarial, supervisao, risco ou alocacao de capacidades EY.\n"
    "4. Fontes: Sem fontes relevantes."
)


def load_env_file(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _safe_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _compact_excerpt(text: str, limit: int = 420) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _is_greeting(message: str) -> bool:
    tokens = set(tokenize(message))
    return bool(tokens) and tokens.issubset(GREETING_TOKENS)


def _looks_in_scope(message: str, area: str | None) -> bool:
    if area:
        return True

    tokens = set(tokenize(message))
    if not tokens:
        return False

    if tokens.intersection(DOMAIN_TERMS):
        return True

    # Product/person names tend to survive tokenization as longer distinctive tokens.
    distinctive_terms = {token for token in tokens if len(token) >= 9}
    return len(distinctive_terms) >= 2


def chunk_to_source(chunk: Chunk, index: int) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "label": f"Fonte {index}",
        "citation": chunk.citation,
        "source_name": chunk.source_name,
        "source_file": str(Path(chunk.source_file).resolve()),
        "source_kind": chunk.source_kind,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "excerpt": _compact_excerpt(chunk.text),
    }


def _rank_sentences(question: str, chunks: list[Chunk], max_sentences: int = 5) -> list[str]:
    query_tokens = set(tokenize(question))
    wants_ey_context = bool(query_tokens.intersection(EY_INTENT_TERMS))
    candidates: list[tuple[float, str]] = []
    seen: set[str] = set()

    for chunk_index, chunk in enumerate(chunks):
        sentences = SENTENCE_RE.split(chunk.text)
        for sentence_index, sentence in enumerate(sentences):
            sentence = _compact_excerpt(sentence, limit=260)
            normalized = sentence.lower()
            if normalized.startswith(("grafico", "gráfico", "fontes:", "fonte:", "notas:", "| notas:")):
                continue
            if normalized.startswith(("facing these threats", "join ey in")):
                continue
            if "gráfico" in normalized and ("painel" in normalized or "fonte:" in normalized):
                continue
            if any(marker in normalized for marker in NOISY_EXTRACT_MARKERS):
                continue
            if len(re.findall(r"\d", sentence)) > max(12, len(sentence) // 4):
                continue
            sentence_tokens = set(tokenize(sentence))
            if len(sentence_tokens) < 4:
                continue
            fingerprint = " ".join(sorted(sentence_tokens))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)

            overlap = len(query_tokens.intersection(sentence_tokens))
            source_bonus = max(0.0, 1.5 - (chunk_index * 0.15))
            if wants_ey_context and chunk.source_kind in {"ey", "spreadsheet"}:
                source_bonus += 2.0
                if any(term in normalized for term in ("developed", "solution", "platform", "partner", "service line")):
                    source_bonus += 1.5
            position_bonus = max(0.0, 0.5 - (sentence_index * 0.03))
            score = overlap * 2.0 + source_bonus + position_bonus
            if score > 0:
                candidates.append((score, sentence))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [sentence for _score, sentence in candidates[:max_sentences]]


def build_extractive_answer(question: str, chunks: list[Chunk]) -> str:
    if not chunks:
        return NO_CONTEXT_ANSWER

    facts = _rank_sentences(question, chunks)
    query_tokens = set(tokenize(question))
    if query_tokens.intersection(EY_INTENT_TERMS):
        ey_facts = _rank_sentences(
            question,
            [chunk for chunk in chunks if chunk.source_kind in {"ey", "spreadsheet"}],
            max_sentences=2,
        )
        if ey_facts and ey_facts[0] not in facts:
            facts = (facts[:4] + [ey_facts[0]])[:5]

    fact_lines = "\n".join(f"- {fact}" for fact in facts[:5]) or "- Contexto encontrado, mas sem frases suficientemente claras para resumo automatico."
    source_lines = "\n".join(f"- [Fonte {index}] {chunk.citation}" for index, chunk in enumerate(chunks, start=1))

    return (
        "1. Sumario executivo: Encontrei contexto relevante na base de conhecimento e preparei uma resposta preliminar com as fontes mais proximas.\n"
        "2. Dados-chave:\n"
        f"{fact_lines}\n"
        "3. Implicacoes para EY: Usa estes sinais para orientar a conversa com o cliente e valida a sintese final no documento original ou com o LLM ativo.\n"
        "4. Fontes:\n"
        f"{source_lines}"
    )


class ChatbotService:
    def __init__(
        self,
        *,
        data_dirs: list[str | Path] | None = None,
        include_pdfs: bool = True,
        include_spreadsheets: bool = True,
        offline: bool = False,
    ) -> None:
        self.data_dirs = [Path(path) for path in (data_dirs or DEFAULT_PROJECT_DATA_DIRS)]
        self.include_pdfs = include_pdfs
        self.include_spreadsheets = include_spreadsheets
        self.offline = offline
        self.chunks: list[Chunk] = []
        self.refresh()

    def refresh(self, *, scrape_first: bool = False) -> None:
        if scrape_first:
            import scraper

            scraper.run()

        self.chunks = load_project_chunks(
            self.data_dirs,
            include_pdfs=self.include_pdfs,
            include_spreadsheets=self.include_spreadsheets,
        )

    @property
    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "chunks": len(self.chunks),
            "sources": len(source_summary(self.chunks)),
            "include_pdfs": self.include_pdfs,
            "include_spreadsheets": self.include_spreadsheets,
            "llm_configured": self._llm_configured(),
            "offline": self.offline,
        }

    def answer(
        self,
        message: str,
        *,
        area: str | None = None,
        top_k: int = 5,
        min_score: float = DEFAULT_MIN_SCORE,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if _is_greeting(message):
            return {
                "answer": (
                    "Ola. Estou ligado ao contexto EY e aos boletins do Banco de Portugal. "
                    "Experimenta perguntar, por exemplo: quais os principais riscos para empresas portuguesas "
                    "e que capacidades da EY podem ajudar?"
                ),
                "sources": [],
                "used_llm": False,
                "warnings": [],
                "prompt": "",
            }

        if not _looks_in_scope(message, area):
            return {
                "answer": OUT_OF_SCOPE_ANSWER,
                "sources": [],
                "used_llm": False,
                "warnings": [],
                "prompt": "",
            }

        scored = score_chunks(message, self.chunks, area=area, min_score=min_score)[:top_k]
        chunks = [chunk for chunk, _score in scored]
        query_tokens = set(tokenize(message))
        if query_tokens.intersection(EY_INTENT_TERMS) and not any(chunk.source_kind in {"ey", "spreadsheet"} for chunk in chunks):
            ey_chunks = [chunk for chunk in self.chunks if chunk.source_kind in {"ey", "spreadsheet"}]
            ey_scored = score_chunks(message, ey_chunks, min_score=0.0)
            if ey_scored:
                chunks = (chunks[: max(top_k - 1, 0)] + [ey_scored[0][0]])[:top_k]

        prompt = build_consultant_prompt(message, chunks, area=area)

        answer_text: str | None = None
        warnings: list[str] = []
        used_llm = False

        if not self.offline and self._llm_configured():
            answer_text, warning = self._call_llm(prompt, history=history)
            if answer_text:
                used_llm = True
            if warning:
                warnings.append(warning)

        if not answer_text:
            answer_text = build_extractive_answer(message, chunks)

        return {
            "answer": answer_text,
            "sources": [chunk_to_source(chunk, index) for index, chunk in enumerate(chunks, start=1)],
            "used_llm": used_llm,
            "warnings": warnings,
            "prompt": prompt,
        }

    def _llm_configured(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def _call_llm(
        self,
        prompt: str,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[str | None, str | None]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None, None

        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        timeout = _safe_int(os.environ.get("OPENAI_TIMEOUT"), default=45, minimum=5, maximum=180)

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are a concise EY Portugal knowledge assistant. "
                    "Answer in European Portuguese and cite the provided sources."
                ),
            }
        ]

        for item in (history or [])[-6:]:
            role = item.get("role", "")
            content = item.get("content", "")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": prompt})

        try:
            body = json.dumps(
                {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            return str(content).strip(), None
        except Exception as exc:  # noqa: BLE001 - API failures should fall back cleanly for demos.
            return None, f"LLM call failed, returned extractive answer instead: {exc}"


class ChatRequestHandler(BaseHTTPRequestHandler):
    service: ChatbotService

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", os.environ.get("CORS_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw_body = self.rfile.read(length)
        return json.loads(raw_body.decode("utf-8"))

    def do_OPTIONS(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler.
        self._send_json({"ok": True})

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler.
        if self.path in {"/health", "/api/health"}:
            self._send_json(self.service.health)
            return

        if self.path in {"/sources", "/api/sources"}:
            self._send_json({"sources": source_summary(self.service.chunks)})
            return

        self._send_json(
            {
                "service": "EY Conversational Agent API",
                "endpoints": ["GET /health", "GET /sources", "POST /chat", "POST /refresh"],
            }
        )

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler.
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON body."}, status=HTTPStatus.BAD_REQUEST)
            return

        if self.path in {"/chat", "/api/chat"}:
            message = str(payload.get("message") or payload.get("question") or "").strip()
            if not message:
                self._send_json({"error": "Field 'message' is required."}, status=HTTPStatus.BAD_REQUEST)
                return

            if payload.get("refresh") or payload.get("scrape"):
                self.service.refresh(scrape_first=bool(payload.get("scrape")))

            top_k = _safe_int(payload.get("top_k"), default=5, minimum=1, maximum=12)
            min_score = _safe_float(payload.get("min_score"), default=DEFAULT_MIN_SCORE, minimum=0.0, maximum=5.0)
            area = payload.get("area")
            history = payload.get("history") if isinstance(payload.get("history"), list) else None

            self._send_json(
                self.service.answer(
                    message,
                    area=str(area) if area else None,
                    top_k=top_k,
                    min_score=min_score,
                    history=history,
                )
            )
            return

        if self.path in {"/refresh", "/api/refresh", "/scrape", "/api/scrape"}:
            self.service.refresh(scrape_first=self.path in {"/scrape", "/api/scrape"} or bool(payload.get("scrape")))
            self._send_json(self.service.health)
            return

        self._send_json({"error": "Unknown endpoint."}, status=HTTPStatus.NOT_FOUND)


def make_handler(service: ChatbotService) -> type[ChatRequestHandler]:
    class Handler(ChatRequestHandler):
        pass

    Handler.service = service
    return Handler


def serve(service: ChatbotService, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"Chatbot API running at http://{host}:{port}")
    print("Frontend endpoint: POST /chat with JSON {'message': '...'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    load_env_file()

    parser = argparse.ArgumentParser(description="Run the integrated EY chatbot backend.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data-dir", action="append", default=None)
    parser.add_argument("--ask", default=None, help="Ask one question in the terminal instead of starting the API.")
    parser.add_argument("--area", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--offline", action="store_true", help="Disable external LLM calls even when OPENAI_API_KEY exists.")
    parser.add_argument("--no-pdfs", action="store_true", help="Skip PDF indexing for faster startup.")
    parser.add_argument("--no-spreadsheets", action="store_true", help="Skip XLSX indexing.")
    parser.add_argument("--scrape-first", action="store_true", help="Run scraper.py before loading the knowledge base.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON for --ask.")
    args = parser.parse_args()

    service = ChatbotService(
        data_dirs=args.data_dir,
        include_pdfs=not args.no_pdfs,
        include_spreadsheets=not args.no_spreadsheets,
        offline=args.offline,
    )

    if args.scrape_first:
        service.refresh(scrape_first=True)

    if args.ask:
        result = service.answer(
            args.ask,
            area=args.area,
            top_k=args.top_k,
            min_score=args.min_score,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["answer"])
            if result["sources"]:
                print("\nSources:")
                for source in result["sources"]:
                    print(f"- {source['label']}: {source['citation']}")
        return

    print(f"Loaded {service.health['chunks']} chunks from {service.health['sources']} sources.")
    serve(service, host=args.host, port=args.port)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - keep command-line failures readable.
        print(f"Error: {exc}", file=sys.stderr)
        raise
