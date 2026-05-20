from pathlib import Path
import argparse

from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Settings, get_settings
from app.loaders import iter_supported_files, load_document
from app.web_sources import check_web_sources, scrape_web_sources


def build_embeddings(settings: Settings | None = None) -> GoogleGenerativeAIEmbeddings:
    settings = settings or get_settings()
    if not settings.resolved_google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required to build Gemini embeddings.")

    return GoogleGenerativeAIEmbeddings(
        model=settings.gemini_embedding_model,
        google_api_key=settings.resolved_google_api_key,
    )


def build_vector_store(settings: Settings | None = None) -> Chroma:
    settings = settings or get_settings()
    return Chroma(
        collection_name=settings.collection_name,
        persist_directory=str(settings.chroma_path),
        embedding_function=build_embeddings(settings),
    )


def get_processed_sources(vector_store: Chroma) -> set[str]:
    try:
        metadatas = vector_store.get(include=["metadatas"]).get("metadatas", [])
    except Exception:
        return set()
    return {metadata.get("source") for metadata in metadatas if metadata and metadata.get("source")}


def split_documents(documents, settings: Settings):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    for chunk in chunks:
        chunk.metadata = {
            key: value
            for key, value in chunk.metadata.items()
            if value is not None and isinstance(value, str | int | float | bool)
        }
    return chunks


def index_files(file_paths: list[Path], settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    vector_store = build_vector_store(settings)
    documents = []

    for path in file_paths:
        try:
            vector_store.delete(where={"source": path.name})
        except Exception:
            pass
        documents.extend(load_document(path))

    chunks = split_documents(documents, settings)
    if chunks:
        vector_store.add_documents(chunks)
    return len(chunks)


def ingest_all(settings: Settings | None = None, force: bool = False, include_web: bool = False) -> int:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    vector_store = build_vector_store(settings)
    processed_sources = set() if force else get_processed_sources(vector_store)
    files_to_index = [
        path for path in iter_supported_files(settings.data_dir)
        if force or path.name not in processed_sources
    ]

    documents = []
    for path in files_to_index:
        documents.extend(load_document(path))

    if include_web:
        web_documents = scrape_web_sources()
        documents.extend(
            doc for doc in web_documents
            if force or doc.metadata.get("source") not in processed_sources
        )

    if not documents:
        return 0

    chunks = split_documents(documents, settings)
    if chunks:
        vector_store.add_documents(chunks)
    return len(chunks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index EY challenge documents into ChromaDB.")
    parser.add_argument("--force", action="store_true", help="Re-index all local files.")
    parser.add_argument("--include-web", action="store_true", help="Scrape and index the public challenge sources.")
    parser.add_argument("--check-web", action="store_true", help="Fetch web sources and print a summary without indexing.")
    args = parser.parse_args()

    if args.check_web:
        checks = check_web_sources()
        for item in checks:
            print(
                f"- {item['source']}: {item['status']} | "
                f"{item.get('chars', 0)} chars | {item.get('documents', 0)} base docs | {item['url']}"
            )
            if item.get("message"):
                print(f"  reason: {item['message']}")
            for link in item.get("links", [])[:4]:
                print(f"  link: {link}")

        print("\nFetching indexable web documents...")
        web_docs = scrape_web_sources()
        print(f"Fetched {len(web_docs)} web documents.")
        for doc in web_docs:
            title = doc.metadata.get("title", "Untitled")
            url = doc.metadata.get("url", "")
            chars = len(doc.page_content)
            print(f"- {doc.metadata.get('source')}: {title} ({chars} chars) {url}")
        raise SystemExit(0)

    count = ingest_all(force=args.force, include_web=args.include_web)
    print(f"Indexed {count} chunks into ChromaDB.")
