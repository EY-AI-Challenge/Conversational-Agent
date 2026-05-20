from langchain_ollama import ChatOllama
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.memory import ConversationBufferWindowMemory
from langchain_core.prompts import PromptTemplate

LLM_MODEL = "llama3.2"

SYSTEM_PROMPT = """És um assistente de conhecimento interno da EY Portugal.
Tens acesso a informação sobre partners, service lines, projectos e documentos internos da EY.

Regras:
- Responde SEMPRE em português europeu
- Sê directo e profissional
- Quando souberes o nome do partner responsável, menciona-o
- Se não souberes a resposta, diz claramente que não tens essa informação
- Cita a fonte quando possível (ex: "De acordo com o CV do partner...")

Contexto relevante encontrado:
{context}

Histórico da conversa:
{chat_history}

Pergunta: {question}

Resposta:"""


def build_agent(retriever):
    llm = ChatOllama(
        model=LLM_MODEL,
        temperature=0.1,      # respostas mais factuais, menos criativas
        num_ctx=4096,         # context window
    )

    memory = ConversationBufferWindowMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer",
        k=5,                  # guarda as últimas 5 trocas
    )

    prompt = PromptTemplate(
        input_variables=["context", "chat_history", "question"],
        template=SYSTEM_PROMPT,
    )

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": prompt},
        verbose=False,
    )

    return chain


def ask(chain, question: str, partner_lookup=None, person_lookup=None) -> dict:
    if person_lookup is not None:
        lookup_result = person_lookup.answer(question)
        if lookup_result is not None:
            return lookup_result

    if partner_lookup is not None:
        lookup_result = partner_lookup.answer(question)
        if lookup_result is not None:
            return lookup_result

    result = chain.invoke({"question": question})
    return {
        "answer": result["answer"],
        "sources": [
            doc.metadata.get("source", "Desconhecido")
            for doc in result.get("source_documents", [])
        ]
    }
