from pathlib import Path
import json

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.rag_chain import RAGSystem
from app.schemas import ChatRequest, ChatResponse, HealthResponse, SourceSummary, UploadResponse


settings = get_settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name)
rag = RAGSystem(settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    status = "ready" if rag.is_ready else f"not_ready: {rag.startup_error}"
    return HealthResponse(
        status=status,
        collection_name=settings.collection_name,
        documents_indexed=rag.count_chunks(),
        data_dir=str(settings.data_dir),
    )


@app.post("/chat", response_model=ChatResponse)
@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        answer, sources = rag.ask(
            question=request.question,
            history=request.history,
            filters=request.filters,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(answer=answer, sources=sources)


@app.post("/chat/stream")
@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    def event_stream():
        try:
            sources, chunks = rag.stream_answer(
                question=request.question,
                history=request.history,
                filters=request.filters,
            )
            yield json.dumps(
                {"type": "sources", "sources": [source.model_dump() for source in sources]},
                ensure_ascii=False,
            ) + "\n"
            for chunk in chunks:
                yield json.dumps({"type": "token", "content": chunk}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"
        except RuntimeError as exc:
            yield json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.get("/sources", response_model=list[SourceSummary])
@app.get("/api/sources", response_model=list[SourceSummary])
def sources() -> list[SourceSummary]:
    return [SourceSummary(**item) for item in rag.source_summaries()]


@app.post("/upload", response_model=UploadResponse)
@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".pdf", ".txt", ".md", ".xlsx", ".xls", ".csv"}:
        raise HTTPException(status_code=400, detail="Formato não suportado.")

    destination = settings.upload_dir / Path(file.filename).name
    content = await file.read()
    destination.write_bytes(content)

    try:
        chunks = rag.index_uploaded_file(destination)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return UploadResponse(
        filename=destination.name,
        chunks_indexed=chunks,
        message="Documento carregado e indexado com sucesso.",
    )
