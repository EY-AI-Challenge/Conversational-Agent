from __future__ import annotations

import os
import time
from typing import Any

import requests
import streamlit as st


DEFAULT_API_URL = os.environ.get("CHATBOT_API_URL", "http://127.0.0.1:8000/chat")

AREA_OPTIONS = {
    "Sem filtro": None,
    "Macroeconomia / inflacao": "inflacao",
    "Credito e PMEs": "credito",
    "Energia": "energia",
    "Risco e fraude": "risco",
    "EY interno": "ey",
    "Inteligencia artificial": "ia",
}


def call_chatbot(
    api_url: str,
    message: str,
    *,
    area: str | None,
    history: list[dict[str, str]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": message,
        "area": area,
        "top_k": 5,
        "history": history[-8:],
    }
    response = requests.post(api_url, json=payload, timeout=90)
    response.raise_for_status()
    return response.json()


def check_health(api_url: str) -> dict[str, Any] | None:
    health_url = api_url.rstrip("/")
    if health_url.endswith("/chat"):
        health_url = health_url[: -len("/chat")] + "/health"
    elif health_url.endswith("/api/chat"):
        health_url = health_url[: -len("/api/chat")] + "/api/health"

    try:
        response = requests.get(health_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


st.set_page_config(
    page_title="Smart Supervision - EY AI Challenge",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main-title {
        color: #FFE600;
        background-color: #1E1E1E;
        padding: 18px 22px;
        border-radius: 8px;
        font-weight: 700;
    }
    .main-title h1 {
        margin: 0;
        font-size: 2rem;
        letter-spacing: 0;
    }
    .stButton>button {
        background-color: #FFE600;
        color: #111111;
        border-radius: 5px;
        border: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='main-title'><h1>Smart Supervision</h1></div>", unsafe_allow_html=True)
st.caption("EY knowledge assistant for BdP and internal information")

with st.sidebar:
    st.markdown("## EY | Smart Supervision")
    api_url = st.text_input("Backend URL", value=DEFAULT_API_URL)
    selected_area_label = st.selectbox("Area", list(AREA_OPTIONS.keys()))
    selected_area = AREA_OPTIONS[selected_area_label]

    health = check_health(api_url)
    if health:
        st.success(f"{health.get('chunks', 0)} chunks | {health.get('sources', 0)} sources")
        st.caption("LLM active" if health.get("llm_configured") else "Extractive mode")
    else:
        st.error("Backend unavailable")
        st.caption("Start it with: python chatbot.py --host 127.0.0.1 --port 8000")

    if st.button("Limpar conversa"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Ola. Sou o Smart Supervision, ligado ao contexto EY e aos boletins BdP. "
                "Que informacao queres analisar?"
            ),
        }
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        for source in message.get("sources", []):
            with st.expander(source.get("citation", "Fonte")):
                st.caption(source.get("source_file", ""))
                st.write(source.get("excerpt", ""))

if prompt := st.chat_input("Pergunta sobre BdP, risco, equipas EY, IA ou servicos internos"):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        placeholder = st.empty()
        try:
            result = call_chatbot(
                api_url,
                prompt,
                area=selected_area,
                history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in st.session_state.messages
                    if item["role"] in {"user", "assistant"}
                ],
            )
            answer = result.get("answer", "")
            rendered = ""
            for line in answer.splitlines():
                rendered += line + "\n"
                placeholder.markdown(rendered)
                time.sleep(0.015)

            sources = result.get("sources", [])
            for source in sources:
                with st.expander(source.get("citation", "Fonte")):
                    st.caption(source.get("source_file", ""))
                    st.write(source.get("excerpt", ""))

            warnings = result.get("warnings", [])
            for warning in warnings:
                st.warning(warning)

            st.caption("Resposta gerada com LLM" if result.get("used_llm") else "Resposta em modo extractivo")

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                    "sources": sources,
                }
            )
        except requests.RequestException as exc:
            error = (
                "Nao consegui contactar o backend do chatbot. "
                "Confirma que `chatbot.py` esta a correr e que o URL no painel lateral esta correto.\n\n"
                f"Detalhe: `{exc}`"
            )
            placeholder.error(error)
            st.session_state.messages.append({"role": "assistant", "content": error})
