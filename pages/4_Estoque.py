# pages/3_📦_Estoque.py

import streamlit as st
import pandas as pd
import sqlite3

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
# Checa se o usuário está logado
if not st.session_state.get("logged_in", False):
    st.error("Por favor, faça o login para acessar esta página.")
    st.stop()



# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(layout="wide")
st.title("📦 Análise de Estoque")

# --- FUNÇÕES ---

def criar_conexao():
    """Cria e retorna uma conexão com o banco de dados."""
    return sqlite3.connect('gestor.db')

def formatar_numero(valor):
    """Formata um número como inteiro com separador de milhar."""
    try:
        # Arredonda para o inteiro mais próximo antes de formatar
        return f'{int(round(valor, 0)):,}'.replace(',', '.')
    except (ValueError, TypeError):
        return "0"

@st.cache_data
def verificar_e_carregar_dados():
    """
    Verifica a integridade dos dados e carrega o estoque.
    Retorna um DataFrame e uma mensagem de status.
    """
    try:
        conn = criar_conexao()
        cursor = conn.cursor()

        # 1. Verificar se a tabela 'produtos' tem dados
        cursor.execute("SELECT COUNT(*) FROM produtos")
        contagem_produtos = cursor.fetchone()[0]
        if contagem_produtos == 0:
            return pd.DataFrame(), "A lista de produtos está vazia. Por favor, importe o arquivo `produtos.xlsx` na página '💾 Dados'."

        # 2. Verificar se a tabela 'estoque' tem dados
        cursor.execute("SELECT COUNT(*) FROM estoque")
        contagem_estoque = cursor.fetchone()[0]
        if contagem_estoque == 0:
            return pd.DataFrame(), "A tabela de estoque está vazia. Por favor, importe os arquivos de estoque (hub1, hub3, etc.) na página '💾 Dados'."

        # 3. Verificar se há correspondência entre produtos e estoque
        query_join = """
        SELECT COUNT(*) 
        FROM produtos p 
        INNER JOIN estoque e ON p.CodPro = e.CodPro
        """
        cursor.execute(query_join)
        contagem_join = cursor.fetchone()[0]
        if contagem_join == 0:
            return pd.DataFrame(), "Importação de estoque detectada, mas os códigos dos produtos (`CodPro`) nos arquivos de estoque não correspondem a nenhum código na sua lista de produtos. Verifique se o arquivo `produtos.xlsx` está atualizado antes de importar o estoque."

        # 4. Se tudo estiver correto, carregar os dados
        query_final = """
        SELECT
            p.CodPro,
            p.Descricao,
            p.m2,
            COALESCE(e.Estoque_1, 0) as Hub1,
            COALESCE(e.Estoque_3, 0) as Hub3,
            COALESCE(e.Estoque_19, 0) as Hub19
        FROM produtos p
        JOIN estoque e ON p.CodPro = e.CodPro
        WHERE COALESCE(e.Estoque_1, 0) + COALESCE(e.Estoque_3, 0) + COALESCE(e.Estoque_19, 0) > 0
        """
        df = pd.read_sql_query(query_final, conn)
        conn.close()
        
        # Previne erro de divisão por zero no cálculo de rolos
        df['m2'] = df['m2'].fillna(1)
        df.loc[df['m2'] == 0, 'm2'] = 1
        
        return df, "Dados carregados com sucesso."

    except Exception as e:
        # Captura outros possíveis erros de banco de dados
        return pd.DataFrame(), f"Erro ao acessar o banco de dados: {e}"

# --- LÓGICA PRINCIPAL ---

placeholder_cards = st.empty() # Cria um espaço reservado no topo
df_estoque, status_mensagem = verificar_e_carregar_dados()

if df_estoque.empty:
    st.warning(status_mensagem)
else:
    # --- CONTROLES (ficam abaixo dos cards visualmente) ---
    unidade = st.radio("Unidade de Medida:", ('m²', 'Rolo'), horizontal=True, key='unidade_estoque')
    termo_pesquisa = st.text_input("Pesquisar por Código ou Descrição:", "")

    # --- FILTRO DE PESQUISA ---
    df_filtrado = df_estoque
    if termo_pesquisa:
        df_filtrado = df_estoque[
            df_estoque['CodPro'].astype(str).str.contains(termo_pesquisa, case=False, na=False) |
            df_estoque['Descricao'].str.contains(termo_pesquisa, case=False, na=False)
        ]
    
    # --- LÓGICA DOS CARDS (Preenche o espaço reservado no topo) ---
    with placeholder_cards.container():
        total_itens = len(df_filtrado)
        
        if unidade == 'm²':
            total_hub1 = df_filtrado['Hub1'].sum()
            total_hub3 = df_filtrado['Hub3'].sum()
            total_hub19 = df_filtrado['Hub19'].sum()
        else:  # Rolo
            total_hub1 = (df_filtrado['Hub1'] / df_filtrado['m2']).sum()
            total_hub3 = (df_filtrado['Hub3'] / df_filtrado['m2']).sum()
            total_hub19 = (df_filtrado['Hub19'] / df_filtrado['m2']).sum()

        estoque_total = total_hub1 + total_hub3 + total_hub19

        st.write("---")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            with st.container(border=True): st.metric("Total de Itens", formatar_numero(total_itens))
        with col2:
            with st.container(border=True): st.metric(f"Total Hub 1", formatar_numero(total_hub1))
        with col3:
            with st.container(border=True): st.metric(f"Total Hub 3", formatar_numero(total_hub3))
        with col4:
            with st.container(border=True): st.metric(f"Total Hub 19", formatar_numero(total_hub19))
        with col5:
            with st.container(border=True): st.metric(f"Estoque Total", formatar_numero(estoque_total))
        st.write("---")
    
    # --- TABELA DE DADOS ---
    if df_filtrado.empty:
        st.info("Nenhum produto encontrado para a pesquisa.")
    else:
        df_display = pd.DataFrame()
        df_display['Produto'] = df_filtrado['CodPro'].astype(str) + ' - ' + df_filtrado['Descricao']
        
        if unidade == 'm²':
            df_display['Hub 1'] = df_filtrado['Hub1']
            df_display['Hub 3'] = df_filtrado['Hub3']
            df_display['Hub 19'] = df_filtrado['Hub19']
        else:  # Rolo
            df_display['Hub 1'] = df_filtrado['Hub1'] / df_filtrado['m2']
            df_display['Hub 3'] = df_filtrado['Hub3'] / df_filtrado['m2']
            df_display['Hub 19'] = df_filtrado['Hub19'] / df_filtrado['m2']
        
        df_display['Total'] = df_display[['Hub 1', 'Hub 3', 'Hub 19']].sum(axis=1)
        df_display = df_display.sort_values(by='Total', ascending=False).reset_index(drop=True)
        
        colunas_numericas = ['Hub 1', 'Hub 3', 'Hub 19', 'Total']
        format_dict = {
            col: lambda x: f'{int(round(x, 0)):,}'.replace(',', '.') for col in colunas_numericas
        }
        
        styled_df = df_display.style.format(format_dict).set_properties(
            subset=colunas_numericas, **{'text-align': 'right'}
        )
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True
        )