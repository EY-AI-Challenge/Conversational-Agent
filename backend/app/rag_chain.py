from collections import Counter
from pathlib import Path
from collections.abc import Iterator
import re

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import Settings, get_settings
from app.ingest import build_vector_store, ingest_all, index_files
from app.prompts import api_key_help_text, build_history_text, load_assistant_prompt
from app.schemas import Message, Source


METADATA_STOPWORDS = {
    "que",
    "diz",
    "documento",
    "document",
    "sobre",
    "resume",
    "resumo",
    "qual",
    "quais",
    "como",
    "para",
    "uma",
    "com",
    "pdf",
}


class RAGSystem:
    """Gemini-powered RAG system over EY internal challenge data."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.vector_store = None
        self.llm = None
        self._ready = False
        self._startup_error: str | None = None
        self._initialize()

    def _initialize(self) -> None:
        try:
            if not self.settings.resolved_google_api_key:
                self._startup_error = api_key_help_text()
                return

            self.vector_store = build_vector_store(self.settings)
            ingest_all(self.settings, include_web=self.settings.web_sources_enabled)
            self.llm = ChatGoogleGenerativeAI(
                model=self.settings.gemini_model,
                google_api_key=self.settings.resolved_google_api_key,
                temperature=0.2,
            )
            self._ready = True
        except Exception as exc:
            self._startup_error = str(exc)
            self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def startup_error(self) -> str | None:
        return self._startup_error

    def ensure_ready(self) -> None:
        if not self._ready:
            raise RuntimeError(self._startup_error or "RAG system is not ready.")

    def retrieve(self, question: str, filters: list[str] | None = None) -> list[tuple[Document, float]]:
        self.ensure_ready()
        search_filter = None
        if filters:
            search_filter = {"document_type": {"$in": filters}}

        semantic_docs = self.vector_store.similarity_search_with_relevance_scores(
            question,
            k=self.settings.retrieval_k,
            filter=search_filter,
        )
        metadata_docs = self._metadata_matches(question, filters)
        return self._merge_ranked_documents(metadata_docs + semantic_docs)

    def _metadata_matches(self, question: str, filters: list[str] | None = None) -> list[tuple[Document, float]]:
        tokens = self._search_tokens(question)
        if not tokens:
            return []

        try:
            stored = self.vector_store.get(include=["documents", "metadatas"])
        except Exception:
            return []

        matches: list[tuple[Document, float]] = []
        for text, metadata in zip(stored.get("documents", []), stored.get("metadatas", []), strict=False):
            if not metadata:
                continue
            if filters and metadata.get("document_type") not in filters:
                continue

            metadata_text = " ".join(
                str(metadata.get(key, ""))
                for key in ("source", "title", "document_type", "service_line")
            )
            metadata_tokens = self._search_tokens(metadata_text)
            if tokens.intersection(metadata_tokens):
                matches.append((Document(page_content=text, metadata=metadata), 1.1))
            if len(matches) >= self.settings.retrieval_k:
                break

        return matches

    def _search_tokens(self, value: str) -> set[str]:
        raw_tokens = re.findall(r"[\w]+", value.lower(), flags=re.UNICODE)
        return {
            token
            for token in raw_tokens
            if len(token) >= 3 and token not in METADATA_STOPWORDS
        }

    def _merge_ranked_documents(self, docs_with_scores: list[tuple[Document, float]]) -> list[tuple[Document, float]]:
        merged: list[tuple[Document, float]] = []
        seen = set()
        for doc, score in sorted(docs_with_scores, key=lambda item: item[1], reverse=True):
            key = (
                doc.metadata.get("source"),
                doc.metadata.get("page"),
                doc.page_content[:120],
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append((doc, score))
            if len(merged) >= self.settings.retrieval_k:
                break
        return merged

    def format_context(self, docs_with_scores: list[tuple[Document, float]]) -> str:
        context_parts = []
        for index, (doc, score) in enumerate(docs_with_scores, start=1):
            metadata = doc.metadata
            source = metadata.get("source", "Documento desconhecido")
            page = metadata.get("page")
            document_type = metadata.get("document_type", "internal")
            service_line = metadata.get("service_line")

            meta_bits = [f"Fonte: {source}", f"Tipo: {document_type}", f"Score: {score:.3f}"]
            if page:
                meta_bits.append(f"Página: {page}")
            if service_line:
                meta_bits.append(f"Service line: {service_line}")

            context_parts.append(f"[Documento {index} | {' | '.join(meta_bits)}]\n{doc.page_content}")
        return "\n\n---\n\n".join(context_parts)

    def build_sources(self, docs_with_scores: list[tuple[Document, float]]) -> list[Source]:
        deduped: dict[tuple, Source] = {}
        for doc, score in docs_with_scores:
            metadata = doc.metadata
            key = (metadata.get("source"), metadata.get("page"), metadata.get("document_type"))
            if key in deduped:
                continue
            deduped[key] = Source(
                source=metadata.get("source", "Documento desconhecido"),
                document_type=metadata.get("document_type", "internal"),
                page=metadata.get("page"),
                title=metadata.get("title"),
                service_line=metadata.get("service_line"),
                url=metadata.get("url"),
                score=round(float(score), 4),
                excerpt=doc.page_content[:240].replace("\n", " ").strip(),
            )
        return list(deduped.values())

    def _select_documents(self, question: str, filters: list[str] | None = None) -> list[tuple[Document, float]]:
        docs_with_scores = self.retrieve(question, filters)
        return [
            item for item in docs_with_scores
            if item[1] >= self.settings.min_relevance_score
        ] or docs_with_scores[:3]

    def ask(self, question: str, history: list[Message] | None = None, filters: list[str] | None = None) -> tuple[str, list[Source]]:
        strong_docs = self._select_documents(question, filters)

        if not strong_docs:
            return (
                "Não encontrei evidência suficiente nos documentos indexados para responder com segurança. "
                "Tenta reformular a pergunta ou carregar mais documentação relevante.",
                [],
            )

        prompt = ChatPromptTemplate.from_template(load_assistant_prompt())
        chain = prompt | self.llm
        answer = chain.invoke(
            {
                "context": self.format_context(strong_docs),
                "history": build_history_text(history or []),
                "question": question,
            }
        )
        content = answer.content if hasattr(answer, "content") else str(answer)
        return content, self.build_sources(strong_docs)

    def stream_answer(
        self,
        question: str,
        history: list[Message] | None = None,
        filters: list[str] | None = None,
    ) -> tuple[list[Source], Iterator[str]]:
        strong_docs = self._select_documents(question, filters)

        if not strong_docs:
            message = (
                "Não encontrei evidência suficiente nos documentos indexados para responder com segurança. "
                "Tenta reformular a pergunta ou carregar mais documentação relevante."
            )
            return [], iter([message])

        prompt = ChatPromptTemplate.from_template(load_assistant_prompt())
        chain = prompt | self.llm
        stream = chain.stream(
            {
                "context": self.format_context(strong_docs),
                "history": build_history_text(history or []),
                "question": question,
            }
        )

        def token_iterator() -> Iterator[str]:
            for chunk in stream:
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    yield content

        return self.build_sources(strong_docs), token_iterator()

    def index_uploaded_file(self, path: Path) -> int:
        self.ensure_ready()
        chunks = index_files([path], self.settings)
        self.vector_store = build_vector_store(self.settings)
        return chunks

    def count_chunks(self) -> int:
        if not self.vector_store:
            return 0
        try:
            return len(self.vector_store.get(include=[]).get("ids", []))
        except Exception:
            return 0

    def source_summaries(self) -> list[dict]:
        if not self.vector_store:
            return []
        try:
            metadatas = self.vector_store.get(include=["metadatas"]).get("metadatas", [])
        except Exception:
            return []

        counter = Counter(
            (
                metadata.get("source", "Documento desconhecido"),
                metadata.get("document_type", "internal"),
            )
            for metadata in metadatas
            if metadata
        )
        return [
            {"source": source, "document_type": document_type, "chunks": chunks}
            for (source, document_type), chunks in sorted(counter.items())
        ]
