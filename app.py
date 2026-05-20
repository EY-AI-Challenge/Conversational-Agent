import streamlit as st
import time

# Configuração da página da EY
st.set_page_config(
    page_title="Smart Supervision - EY AI Challenge",
    page_icon="🔎",
    layout="wide"
)

# Estilo visual para as cores da EY (Preto e Amarelo)
st.markdown("""
    <style>
    .main-title { color: #FFE600; background-color: #1E1E1E; padding: 20px; border-radius: 10px; text-align: center; font-weight: bold; }
    .stButton>button { background-color: #FFE600; color: black; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='main-title'><h1>🔎 Smart Supervision</h1></div>", unsafe_allow_html=True)
st.caption("Estratégia EY: Centralização de Inteligência para o Banco de Portugal")

# --- SIDEBAR: FOCO EXCLUSIVO NO BANCO DE PORTUGAL ---
st.sidebar.markdown("## 🌐 EY | Smart Supervision")
st.sidebar.header("🎯 Painel de Controlo")

# Filtragem de informação (A tua Ideia Original de filtrar por áreas)
area_selecionada = st.sidebar.selectbox(
    "Âmbito da Supervisão:",
    ["Análise Macro (Boletins)", "Riscos de Crédito PMEs", "Monitorização de Inflação", "Estabilidade Financeira"]
)

st.sidebar.subheader("📊 Fontes BdP Ativas")
st.sidebar.success("✅ Boletins Económicos Mensais")
st.sidebar.success("✅ Relatórios de Estabilidade")
st.sidebar.success("✅ Estatísticas de Crédito")

st.sidebar.markdown("---")
st.sidebar.info("💡 **A nossa tese:** 'Se a EY automatiza a sua inteligência interna, o Smart Supervision permite ao BdP modernizar anos de relatórios num único motor de decisão.'")

# --- CONTEXTO DO PROBLEMA (A tua estrutura de Pitch) ---
with st.expander("📌 Porquê o Smart Supervision?"):
    st.markdown("""
    * **O Problema:** Os profissionais perdem cerca de 2 semanas a navegar em centenas de PDFs do BdP para detetar um único risco.
    * **A Solução:** O Smart Supervision organiza dados de supervisão e responde a questões complexas de forma clara e filtrada por área.
    * **Impacto:** Redução do tempo de análise e clarificação imediata da resiliência dos bancos face a riscos climáticos e digitais.
    """)

# --- HISTÓRICO DO CHAT ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Olá! Sou o Smart Supervision, o motor de inteligência desenhado pela EY para o Banco de Portugal. Que dados de supervisão queres analisar agora?"}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- LÓGICA DE INTERAÇÃO (Foco BdP e perguntas do teu rascunho) ---
if prompt := st.chat_input("Como está a tendência da inflação ou o risco das PMEs?"):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        p_lower = prompt.lower()
        
        # Respostas inteligentes baseadas nos teus rascunhos da Fase 4
        if "inflação" in p_lower or "tendência" in p_lower:
            response = """
### 📈 Análise de Supervisão: Tendência de Inflação
Com base nos últimos 3 Boletins Económicos do BdP, detetámos uma convergência da inflação para o objetivo de 2%, embora a inflação nos serviços permaneça sob vigilância devido ao dinamismo do mercado de trabalho.

**Dados Críticos para o BdP:**
* **HICP Recente:** 2.3% (em linha com as projeções macroeconómicas).
* **Risco Detetado:** Persistência de pressões salariais no setor de serviços e turismo.
* **Fonte:** *Boletim Económico BdP - Secção 2: Evolução Macroeconómica, pág. 12.*
            """
        elif "crédito" in p_lower or "pme" in p_lower or "endividamento" in p_lower:
            response = """
### 🏢 Análise de Supervisão: Resiliência Empresarial
O Smart Supervision identificou que o rácio de endividamento das PMEs portuguesas continua a baixar, mas a capacidade de serviço da dívida está sob pressão em setores dependentes de taxas variáveis.

**Foco de Supervisão:**
* **Alerta de Risco:** Deterioração do rácio de cobertura de juros em 15% das PMEs industriais analisadas.
* **Recomendação EY:** Aumentar preventivamente as provisões para risco de crédito nestes clusters específicos.
* **Fonte:** *Relatório de Estabilidade Financeira BdP - Capítulo de Resiliência do Setor Privado, pág. 45.*
            """
        elif "partner" in p_lower or "equipa" in p_lower or "alocação" in p_lower or "sócio" in p_lower:
            response = """
### 💼 2ª Solução: Alocação e Disponibilidade de Especialistas EY
Para operacionalizar estes dados e apresentar a solução ao conselho do BdP, o sistema identificou os perfis ideais na nossa matriz de competências interna (baseada no ficheiro Excel da EY):

| Sócio / Partner | Service Line | Especialidade | Disponibilidade Atual |
| :--- | :--- | :--- | :--- |
| **Partner Gonçalo Matos** | Consulting - FSO | Inteligência Artificial & Arquitetura de Dados | 🟢 Alta (Disponível de imediato) |
| **Partner Alexandra Silva** | Assurance / Risk | Regulação Bancária & Compliance BdP | 🟡 Média (Livre a partir de sexta-feira) |
| **Partner Manuel Santos** | Strategy and Transactions | Transição Verde & Sustentabilidade (ESG) | 🟢 Alta (Disponível de imediato) |

*Fonte: EY Internal Information - Mapeamento de Service Lines e Partners 2026.*
            """
        else:
            response = """
### 🔍 Smart Supervision - Processamento de Informação
O sistema cruzou com sucesso a sua questão com os dados carregados do Banco de Portugal.

Para uma demonstração detalhada no vosso Pitch, experimente perguntar especificamente por:
1. **"Qual é a tendência da inflação?"** (Testar o Agente Macroeconómico)
2. **"Como está o endividamento das PMEs?"** (Testar o Agente de Supervisão de Risco)
3. **"Quem é a equipa de partners alocada?"** (Testar a 2ª Solução de Alocação da EY)
            """
        
        # Efeito visual de digitação (Streaming)
        full_res = ""
        for line in response.split("\n"):
            full_res += line + "\n"
            message_placeholder.markdown(full_res)
            time.sleep(0.04)
            
        st.session_state.messages.append({"role": "assistant", "content": response})