from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_chroma import Chroma


def build_hybrid_retriever(
    vectorstore: Chroma,
    docs: list,
    k: int = 5,
    bm25_weight: float = 0.4,
    semantic_weight: float = 0.6,
) -> EnsembleRetriever:
    """
    Hybrid Retriever = BM25 (keywords) + MMR (semântica).

    BM25  → encontra nomes exactos: partners, projectos, service lines
    MMR   → encontra conceitos: IA, sustentabilidade, transformação digital
    """

    # Motor 1 — BM25 (keywords)
    bm25_retriever = BM25Retriever.from_documents(docs)
    bm25_retriever.k = k

    # Motor 2 — Semântico com MMR (diversidade + relevância)
    semantic_retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": k,
            "fetch_k": k * 4,   # busca 20, devolve os 5 mais diversos
        }
    )

    # Ensemble — combina os dois motores
    hybrid = EnsembleRetriever(
        retrievers=[bm25_retriever, semantic_retriever],
        weights=[bm25_weight, semantic_weight],
    )

    return hybrid
