from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str = Field(description="Message author: user or assistant")
    content: str


class Source(BaseModel):
    source: str
    document_type: str = "internal"
    page: int | None = None
    title: str | None = None
    service_line: str | None = None
    url: str | None = None
    score: float | None = None
    excerpt: str | None = None


class ChatRequest(BaseModel):
    question: str
    history: list[Message] = []
    filters: list[str] = []


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source] = []


class HealthResponse(BaseModel):
    status: str
    collection_name: str
    documents_indexed: int
    data_dir: str


class SourceSummary(BaseModel):
    source: str
    document_type: str
    chunks: int


class UploadResponse(BaseModel):
    filename: str
    chunks_indexed: int
    message: str
