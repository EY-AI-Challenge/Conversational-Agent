# EY Knowledge Assistant

Agente conversacional inteligente para acesso ao conhecimento interno da EY Portugal.

## Stack técnica

| Componente | Tecnologia |
|---|---|
| Frontend | Streamlit |
| LLM | Ollama (llama3.2) |
| Embeddings | Ollama (nomic-embed-text) |
| RAG Framework | LangChain |
| Retriever | Hybrid — BM25 + MMR |
| Vector Store | ChromaDB |

## Estrutura do projecto

```
ey-agent/
├── Data/                  ← coloca aqui todos os ficheiros EY
│   ├── *.pdf              (CVs de partners + artigos)
│   ├── *.txt              (transcrições)
│   └── *.xlsx             (estrutura service lines)
├── chroma_db/             ← gerado automaticamente
├── src/
│   ├── ingestion.py       (carregamento + chunking + indexação)
│   ├── retriever.py       (hybrid retriever BM25 + MMR)
│   └── agent.py           (RAG chain + memória)
├── app.py                 (frontend Streamlit)
├── requirements.txt
└── README.md
```

## Instalação

### 1. Instalar Ollama
```bash
# Mac / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Descarregar modelos necessários
ollama pull llama3.2
ollama pull nomic-embed-text
```

### 2. Instalar dependências Python
```bash
pip install -r requirements.txt
```

### 3. Colocar os dados
```bash
# Copia todos os ficheiros EY para a pasta Data/
cp /caminho/para/ficheiros/* ./Data/
```

### 4. Executar
```bash
streamlit run app.py
```

O agente indexa automaticamente os documentos na primeira execução.
Para re-indexar, clica em "Re-indexar documentos" na sidebar.

## Como funciona

```
Utilizador faz pergunta
        ↓
Hybrid Retriever (BM25 + MMR)
  ├── BM25: encontra nomes exactos (partners, projectos)
  └── MMR:  encontra conceitos semânticos (IA, sustentabilidade)
        ↓
Top 5 chunks mais relevantes
        ↓
LLM (llama3.2) gera resposta em português
        ↓
Streamlit mostra resposta + fontes
```
