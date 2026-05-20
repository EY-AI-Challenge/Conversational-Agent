import streamlit as st
import os
from pathlib import Path
from src.ingestion import ingest, load_vectorstore
from src.retriever import build_hybrid_retriever
from src.agent import build_agent, ask
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.schema import Document
import pandas as pd

# ── Configuração da página ─────────────────────────────────────────────────
st.set_page_config(
    page_title="EY Knowledge Assistant",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS personalizado ──────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Cor de destaque EY (amarelo) */
    .ey-header {
        background-color: #FFE600;
        padding: 16px 24px;
        border-radius: 8px;
        margin-bottom: 24px;
    }
    .ey-header h1 {
        color: #2E2E38;
        margin: 0;
        font-size: 22px;
        font-weight: 700;
    }
    .ey-header p {
        color: #2E2E38;
        margin: 4px 0 0;
        font-size: 13px;
    }
    .source-tag {
        display: inline-block;
        background: #f0f0f0;
        color: #555;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 12px;
        margin: 2px;
    }
    .status-ok  { color: #28a745; font-weight: 600; }
    .status-err { color: #dc3545; font-weight: 600; }
    [data-testid="stChatMessage"] {
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)


# ── Funções de setup ───────────────────────────────────────────────────────
DATA_DIR   = Path("./Data")
CHROMA_DIR = "./chroma_db"


def load_all_docs():
    """Carrega todos os documentos para o BM25 (precisa dos docs raw)."""
    docs = []
    for f in DATA_DIR.glob("*.txt"):
        try:
            loader = TextLoader(str(f), encoding="utf-8")
            docs.extend(loader.load())
        except Exception:
            pass
    for f in DATA_DIR.glob("*.pdf"):
        try:
            loader = PyPDFLoader(str(f))
            docs.extend(loader.load())
        except Exception:
            pass
    for f in DATA_DIR.glob("*.xlsx"):
        try:
            df = pd.read_excel(str(f))
            for _, row in df.iterrows():
                text = " | ".join(
                    f"{col}: {val}" for col, val in row.items() if pd.notna(val)
                )
                docs.append(Document(page_content=text,
                                     metadata={"source": f.name}))
        except Exception:
            pass
    return docs


@st.cache_resource(show_spinner=False)
def setup_agent():
    """Inicializa o agente RAG (corre apenas uma vez por sessão)."""
    chroma_exists = Path(CHROMA_DIR).exists() and any(Path(CHROMA_DIR).iterdir())

    if chroma_exists:
        vectorstore = load_vectorstore()
    else:
        vectorstore = ingest()

    docs      = load_all_docs()
    retriever = build_hybrid_retriever(vectorstore, docs)
    agent     = build_agent(retriever)
    n_docs    = len(docs)

    return agent, n_docs


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 💼 EY Knowledge Assistant")
    st.markdown("---")

    # Botão de (re)ingestão
    if st.button("🔄 Re-indexar documentos", use_container_width=True):
        import shutil
        if Path(CHROMA_DIR).exists():
            shutil.rmtree(CHROMA_DIR)
        st.cache_resource.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("### 📂 Fontes de conhecimento")
    pdfs  = list(DATA_DIR.glob("*.pdf"))
    txts  = list(DATA_DIR.glob("*.txt"))
    excels = list(DATA_DIR.glob("*.xlsx"))
    st.markdown(f"- 📄 **{len(pdfs)}** PDFs (CVs + artigos)")
    st.markdown(f"- 📝 **{len(txts)}** Transcrições")
    st.markdown(f"- 📊 **{len(excels)}** Excel (Partners)")

    st.markdown("---")
    st.markdown("### 💡 Perguntas exemplo")
    example_questions = [
        "Quem é o partner de AI and Data?",
        "O que é o FraudRadar?",
        "Que serviços tem a área de Tax?",
        "Fala-me sobre o Analytics4Vegetation",
        "Quem lidera o Consulting?",
        "Onde fica o escritório da EY?",
    ]
    for q in example_questions:
        if st.button(q, use_container_width=True, key=q):
            st.session_state.pending_question = q

    st.markdown("---")
    st.markdown("### ⚙️ Configuração")
    st.markdown("🤖 **LLM:** Ollama (llama3.2)")
    st.markdown("🔍 **Retriever:** Hybrid BM25 + MMR")
    st.markdown("💾 **Vector Store:** ChromaDB")


# ── Header principal ───────────────────────────────────────────────────────
st.markdown("""
<div class="ey-header">
    <h1>💼 EY Knowledge Assistant</h1>
    <p>Assistente de conhecimento interno — EY Portugal</p>
</div>
""", unsafe_allow_html=True)


# ── Inicialização do agente ────────────────────────────────────────────────
with st.spinner("🔄 A inicializar o agente (primeira vez pode demorar)..."):
    try:
        agent, n_docs = setup_agent()
        st.success(f"✅ Agente pronto — {n_docs} documentos indexados", icon="✅")
    except Exception as e:
        st.error(f"❌ Erro ao inicializar: {e}")
        st.stop()


# ── Estado da conversa ─────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Olá! Sou o assistente de conhecimento da **EY Portugal**. "
                       "Posso ajudá-lo a encontrar informação sobre partners, "
                       "service lines, projectos e muito mais. Como posso ajudar?",
            "sources": []
        }
    ]


# ── Mostrar histórico de mensagens ─────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            unique_sources = list(dict.fromkeys(msg["sources"]))
            source_html = "".join(
                f'<span class="source-tag">📎 {s}</span>'
                for s in unique_sources[:5]
            )
            st.markdown(f"<div>{source_html}</div>", unsafe_allow_html=True)


# ── Input do utilizador ────────────────────────────────────────────────────
# Verifica se há pergunta pendente (vinda do sidebar)
pending = st.session_state.pop("pending_question", None)
user_input = st.chat_input("Faça a sua pergunta sobre a EY...") or pending

if user_input:
    # Mostra mensagem do utilizador
    st.session_state.messages.append({
        "role": "user",
        "content": user_input,
        "sources": []
    })
    with st.chat_message("user"):
        st.markdown(user_input)

    # Gera resposta do agente
    with st.chat_message("assistant"):
        with st.spinner("🔍 A pesquisar nos documentos..."):
            try:
                result  = ask(agent, user_input)
                answer  = result["answer"]
                sources = result["sources"]

                st.markdown(answer)

                if sources:
                    unique = list(dict.fromkeys(sources))
                    source_html = "".join(
                        f'<span class="source-tag">📎 {s}</span>'
                        for s in unique[:5]
                    )
                    st.markdown(f"<div>{source_html}</div>",
                                unsafe_allow_html=True)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources,
                })

            except Exception as e:
                err = f"❌ Erro ao gerar resposta: {e}"
                st.error(err)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": err,
                    "sources": [],
                })
