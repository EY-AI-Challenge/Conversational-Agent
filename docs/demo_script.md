# Demo Script

## Before The Demo

1. Start the backend on `http://localhost:8000`.
2. Start the frontend on `http://localhost:5173`.
3. Open `GET /health` if you want to confirm backend readiness.
4. Confirm ChromaDB has indexed chunks.
5. Keep a Gemini API key configured in `backend/.env`.

## Live Flow

### 1. Open With The Product

Open the frontend and introduce it as Knowledge Navigator EY Assistant: a knowledge assistant for faster retrieval and reuse of EY internal and curated public information.

### 2. Ask A Service-Line Question

Use:

```text
Quem é responsável por esta service line e que contexto devo saber antes de contactar?
```

Point out that the assistant searches the service-line data and returns cited evidence.

### 3. Ask A Partner Preparation Question

Use:

```text
Resume a experiência relevante de um partner para preparar uma reunião com cliente.
```

Show how the response turns profile information into a client-preparation summary.

### 4. Ask For A Client Briefing

Use:

```text
Prepara um briefing curto para cliente usando as fontes disponíveis sobre AI e transformação.
```

Highlight that this is higher-value synthesis, not just keyword search.

### 5. Show Citations

Use:

```text
Que fontes suportam esta resposta?
```

Show the source chips under the answer and the indexed source panel.

### 6. Upload A Document

Upload a CV or internal document using the uploader, wait for indexing, and ask a follow-up question about the uploaded material.

## Fallback Questions

- Que informação existe sobre EY.ai?
- Que documentos falam sobre carreiras na EY?
- Resume o conteúdo das transcrições disponíveis.
- Que fontes existem sobre relatórios de transparência?

## Unsupported Question Test

Ask a question that is not supported by the documents. The assistant should state that the indexed evidence is insufficient rather than hallucinating.
