import pandas as pd
from bs4 import BeautifulSoup

def extrair_tabelas_boletim_local(caminho_ficheiro):
    print(f"A ler dados do ficheiro local: {caminho_ficheiro} ...")
    
    # Abrir o ficheiro HTML guardado localmente
    with open(caminho_ficheiro, 'r', encoding='utf-8') as f:
        conteudo_html = f.read()
        
    soup = BeautifulSoup(conteudo_html, 'html.parser')
    
    tabelas_wrapper = soup.find_all('div', class_='table--wrapper')
    print(f"Encontradas {len(tabelas_wrapper)} tabelas. A processar...")
    
    documentos_para_vdb = []
    
    for idx, wrapper in enumerate(tabelas_wrapper):
        # 1. Extrair o Título da Tabela
        titulo_div = wrapper.find('div', class_='quadro')
        titulo = titulo_div.get_text(strip=True) if titulo_div else f"Projeções Económicas - Tabela {idx+1}"
        
        # 2. Extrair e remover a linha de Notas
        notas_div = wrapper.find('div', class_='fonte-e-nota')
        notas_texto = notas_div.get_text(strip=True) if notas_div else ""
        
        linha_notas = notas_div.find_parent('tr') if notas_div else None
        if linha_notas:
            linha_notas.decompose()
            
        # 3. Converter para DataFrame
        df = pd.read_html(str(wrapper))[0]
        df = df.fillna("")
        
        # 4. Converter para Markdown
        tabela_markdown = df.to_markdown(index=False)
        
        # 5. Criar o documento final
        documento_texto = f"### {titulo}\n\n{tabela_markdown}\n\n**Notas e Metodologia:**\n{notas_texto}"
        
        # 6. Preparar Metadados
        metadados = {
            "fonte": "Banco de Portugal",
            "tipo_documento": "tabela_projecoes",
            "titulo": titulo
        }
        
        documentos_para_vdb.append({
            "page_content": documento_texto,
            "metadata": metadados
        })
        
    return documentos_para_vdb

# Execução (muda o nome do ficheiro para o que guardaste no teu PC)


dados_vdb = extrair_tabelas_boletim_local("")

for doc in dados_vdb:
    print(doc['page_content'][:300] + "...\n")