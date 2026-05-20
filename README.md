# Knowledge Navigator EY Assistant

Knowledge Navigator EY Assistant is a conversational assistant for the EY AI Challenge 2026. It helps professionals retrieve and reuse knowledge spread across partner CVs, service-line spreadsheets, EY news/articles, transcripts, public sources, and other internal documents.

The prototype follows a RAG architecture: documents are loaded with LangChain, enriched with metadata, chunked, embedded with Gemini embeddings, stored in ChromaDB, retrieved semantically, and answered through Gemini via FastAPI and a React TypeScript frontend.

## Features

- Conversational search over curated EY knowledge.
- Cited answers with source names, pages, document type, and excerpts.
- PDF, text, Markdown, Excel, and CSV ingestion.
- CV/document uploader in the frontend with immediate indexing.
- Suggested demo questions for live presentation flow.
- Source-type filters for partner CVs, service lines, news, transcripts, and scraped web sources.
- Reproducible local setup with persistent ChromaDB.

## Architecture

```text
Data documents
  -> LangChain loaders
  -> metadata enrichment
  -> recursive chunking
  -> Gemini embeddings
  -> ChromaDB persistent collection
  -> semantic retriever
  -> controlled RAG prompt
  -> Gemini answer
  -> FastAPI
  -> React TypeScript UI
```

## Repository Structure

```text
backend/
  app/
    main.py          # FastAPI endpoints
    config.py        # environment and path configuration
    loaders.py       # PDF, text, Excel and CSV loading
    ingest.py        # ChromaDB ingestion
    rag_chain.py     # Gemini RAG orchestration
    prompts.py       # prompt helpers
    schemas.py       # API models
frontend/
  src/
    App.tsx
    api/
    components/
    styles/
Data/                # challenge documents
docs/                # strategic and technical material
```

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set:

```bash
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
WEB_SOURCES_ENABLED=false
```

Install the frontend:

```bash
cd ../frontend
npm install
```

## Ingest Documents

From `backend/`:

```bash
source .venv/bin/activate
python -m app.ingest
```

The app indexes files from `Data/` and persists vectors in `chroma_db/`. Generated vector data is intentionally ignored by git and can be rebuilt.

To also scrape and index the public challenge sources, run:

```bash
python -m app.ingest --include-web
```

This fetches curated pages from Diário da República, Infarmed, DGEG, and Banco de Portugal and stores them as `external` chunks. You can also set `WEB_SOURCES_ENABLED=true` in `backend/.env` if you want the backend to include those web sources during startup.

To test the scraping without indexing or calling Gemini embeddings:

```bash
python -m app.ingest --check-web
```

## Run

Backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

## API

- `GET /health` checks API status and indexed chunks.
- `POST /api/chat` asks a grounded question.
- `POST /api/chat/stream` streams a grounded answer as NDJSON chunks.
- `GET /api/sources` lists indexed sources.
- `POST /api/upload` uploads and indexes a PDF, text, Markdown, Excel, or CSV file.

## Demo Questions

- Quem é responsável por esta service line e que contexto devo saber antes de contactar?
- Resume a experiência relevante de um partner para preparar uma reunião com cliente.
- Que conhecimento interno temos sobre AI e transformação?
- Prepara um briefing curto para cliente usando as fontes disponíveis.
- Que fontes suportam esta resposta?

## Limitations

- This is a local prototype, not a production-secured EY system.
- Access control, user permissions, audit logs, and source-level confidentiality rules are roadmap items.
- Answer quality depends on the indexed documents and Gemini API availability.
- The current ChromaDB setup is local; production should use managed storage and evaluation pipelines.

## Next Steps

- Add authentication and document-level permissions.
- Add answer evaluation metrics and feedback collection.
- Integrate additional curated external sources.
- Add streaming responses and optional speech input/output.
- Prepare final strategic and technical slide decks from the docs in `docs/`.
