import os
import pandas as pd
from pathlib import Path
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

DATA_DIR  = Path("./Data")
CHROMA_DIR = "./chroma_db"
EMBED_MODEL = "nomic-embed-text"
COLLECTION  = "ey_knowledge"


def load_txts() -> list[Document]:
    docs = []
    for f in DATA_DIR.glob("*.txt"):
        try:
            loader = TextLoader(str(f), encoding="utf-8")
            loaded = loader.load()
            for doc in loaded:
                doc.metadata["source"] = f.name
                doc.metadata["type"]   = "transcript"
            docs.extend(loaded)
            print(f"  ✅ TXT: {f.name}")
        except Exception as e:
            print(f"  ❌ Erro TXT {f.name}: {e}")
    return docs


def load_pdfs() -> list[Document]:
    docs = []
    for f in DATA_DIR.glob("*.pdf"):
        try:
            loader = PyPDFLoader(str(f))
            loaded = loader.load()
            for doc in loaded:
                doc.metadata["source"] = f.name
                doc.metadata["type"]   = "pdf"
            docs.extend(loaded)
            print(f"  ✅ PDF: {f.name}")
        except Exception as e:
            print(f"  ❌ Erro PDF {f.name}: {e}")
    return docs


def load_excel() -> list[Document]:
    docs = []
    for f in DATA_DIR.glob("*.xlsx"):
        try:
            df = pd.read_excel(str(f))
            for _, row in df.iterrows():
                text = " | ".join(
                    f"{col}: {val}"
                    for col, val in row.items()
                    if pd.notna(val)
                )
                docs.append(Document(
                    page_content=text,
                    metadata={"source": f.name, "type": "excel"}
                ))
            print(f"  ✅ Excel: {f.name} ({len(df)} linhas)")
        except Exception as e:
            print(f"  ❌ Erro Excel {f.name}: {e}")
    return docs


def ingest() -> Chroma:
    print("\n📂 A carregar documentos...")
    docs = []

    txts   = load_txts()
    pdfs   = load_pdfs()
    excels = load_excel()

    docs = txts + pdfs + excels
    print(f"\n📊 Total carregado: {len(docs)} documentos")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = splitter.split_documents(docs)
    print(f"✂️  Total chunks: {len(chunks)}")

    print("\n🔢 A criar embeddings com Ollama (nomic-embed-text)...")
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
        collection_name=COLLECTION,
    )

    print(f"✅ ChromaDB pronto — {len(chunks)} chunks indexados em '{CHROMA_DIR}'")
    return vectorstore


def load_vectorstore() -> Chroma:
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    return Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings,
        collection_name=COLLECTION,
    )
