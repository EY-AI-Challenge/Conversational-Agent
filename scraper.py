import requests
import pandas as pd
from bs4 import BeautifulSoup

def extrair_tabelas_boletim(url):
    # Cabeçalho para simular um navegador e evitar bloqueios (HTTP 403 Forbidden)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"A descarregar dados de: {url} ...")
    resposta = requests.get(url, headers=headers)
    resposta.raise_for_status()  # Para o script se a página não existir
    
    soup = BeautifulSoup(resposta.text, 'html.parser')
    
    # Encontrar todos os contentores de tabelas no boletim
    tabelas_wrapper = soup.find_all('div', class_='table--wrapper')
    print(f"Encontradas {len(tabelas_wrapper)} tabelas. A processar...")
    
    documentos_para_vdb = []
    
    for idx, wrapper in enumerate(tabelas_wrapper):
        # 1. Extrair o Título da Tabela
        titulo_div = wrapper.find('div', class_='quadro')
        titulo = titulo_div.get_text(strip=True) if titulo_div else f"Projeções Económicas - Tabela {idx+1}"
        
        # 2. Extrair e remover a linha de Notas para não partir as colunas
        notas_div = wrapper.find('div', class_='fonte-e-nota')
        notas_texto = notas_div.get_text(strip=True) if notas_div else ""
        
        linha_notas = notas_div.find_parent('tr') if notas_div else None
        if linha_notas:
            linha_notas.decompose()
            
        # 3. Converter para DataFrame
        df = pd.read_html(str(wrapper))[0]
        df = df.fillna("")  # Limpar células NaN
        
        # 4. Converter para Markdown
        tabela_markdown = df.to_markdown(index=False)
        
        # 5. Criar o documento final
        documento_texto = f"### {titulo}\n\n{tabela_markdown}\n\n**Notas e Metodologia:**\n{notas_texto}"
        
        # 6. Preparar Metadados para o ChromaDB
        metadados = {
            "fonte": "Banco de Portugal",
            "url_origem": url,
            "tipo_documento": "tabela_projecoes",
            "titulo": titulo
        }
        
        documentos_para_vdb.append({
            "page_content": documento_texto,
            "metadata": metadados
        })
        
    return documentos_para_vdb

# Execução do Scraper
print("Iniciando o processo de extração do boletim económico...")
url_boletim = "https://www.bportugal.pt/publicacao/boletim-economico-marco-2026"
dados_vdb = extrair_tabelas_boletim(url_boletim)

# Verificar os resultados
for doc in dados_vdb:
    print("-" * 50)
    print(f"Título: {doc['metadata']['titulo']}")
    print("Excerto do conteúdo:")
    # Imprime apenas os primeiros 300 caracteres para verificar o formato
    print(doc['page_content'][:300] + "...\n")