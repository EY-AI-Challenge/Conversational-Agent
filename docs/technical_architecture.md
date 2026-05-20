# Technical Architecture

## Overview

Knowledge Navigator EY Assistant is a Retrieval-Augmented Generation assistant for professional knowledge retrieval. It turns internal EY challenge documents and selected public sources into cited answers through a reproducible Python backend and a React TypeScript frontend.

## Components

- React TypeScript frontend: chat, streaming responses, filters, source citations, suggested questions, and uploader.
- FastAPI backend: `/health`, `/api/chat`, `/api/sources`, and `/api/upload`.
- LangChain ingestion: document loaders, chunking, and orchestration.
- ChromaDB: persistent local vector store.
- Gemini: embeddings and answer generation configured through `GOOGLE_API_KEY`.

## Data Ingestion

The ingestion pipeline reads files from `Data/`:

- PDFs for partner CVs, EY articles, reports, and internal documents.
- Excel for service lines, subservice lines, and responsible partners.
- TXT/Markdown for transcripts and text knowledge.
- CSV for tabular uploads.
- Optional web scraping for selected public challenge sources: Diário da República, Infarmed, DGEG, and Banco de Portugal.

Each document is loaded into LangChain `Document` objects and split with `RecursiveCharacterTextSplitter`.

## Metadata Model

Every chunk includes useful metadata for retrieval and citations:

```python
{
    "source": "filename.pdf",
    "document_type": "partner_cv | service_line | news | transcript | internal",
    "page": 3,
    "title": "optional title",
    "service_line": "optional service line"
}
```

## Retrieval And Generation

1. Chunks are embedded with Gemini embeddings.
2. Vectors are persisted in the `ey_knowledge_navigator` ChromaDB collection.
3. `/api/chat` retrieves top-k semantically relevant chunks.
4. Retrieved chunks are inserted into a strict RAG prompt.
5. Gemini generates a professional answer grounded only in the retrieved context.
6. The API returns the answer plus structured citations.

## Grounding And Citations

The assistant prompt requires:

- answers only from retrieved context;
- uncertainty when evidence is insufficient;
- source names in every grounded answer;
- consulting-style synthesis instead of generic essays.

The frontend also displays source chips under each answer.

## API Contract

- `GET /health`: readiness, collection name, indexed chunk count, and data directory.
- `POST /api/chat`: question, history, optional source-type filters; returns answer and sources.
- `POST /api/chat/stream`: streams source metadata first and then token/chunk events while Gemini generates.
- `GET /api/sources`: indexed sources grouped by document type and chunk count.
- `POST /api/upload`: uploads a supported file and indexes it immediately.

## Security And Governance Roadmap

For production use, the architecture should add:

- SSO and role-based access control;
- document-level permissions before retrieval;
- audit logging for prompts, sources, and responses;
- retention policies for uploaded files;
- monitoring and quality evaluation;
- migration from local ChromaDB to managed vector infrastructure.

## Limitations

- Local vector database only.
- Gemini API key required.
- No enterprise permission model yet.
- Document classification is heuristic and should be replaced by governed metadata in production.
