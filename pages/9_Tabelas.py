import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import os

# --- NOVO BLOCO DE CONTROLE DE ACESSO ---
@st.cache_data(ttl=30)
def get_user_permissions_from_db(_role):
    if not _role: return []
    try:
        conn = sqlite3.connect("gestor_mkt.db", check_same_thread=False)
        query = "SELECT page_name FROM permissoes WHERE role = ?"
        df_perms = pd.read_sql_query(query, conn, params=(_role,))
        conn.close()
        return df_perms['page_name'].tolist()
    except: return []

def check_permission():
    if not st.session_state.get("authentication_status"):
        st.error("Acesso negado. Por favor, faça o login.")
        st.switch_page("app.py")
        st.stop()

    # 2. Garante que as permissões estão carregadas na sessão (essencial para reloads de página)
    if "permissions" not in st.session_state or st.session_state.permissions is None:
        role = st.session_state.get("role")
        if not role: # Se o perfil não existir na sessão, busca de novo
             conn = sqlite3.connect("gestor_mkt.db", check_same_thread=False)
             username = st.session_state.get("username")
             df_user = pd.read_sql_query(f"SELECT role FROM usuarios WHERE username = '{username}'", conn)
             conn.close()
             if not df_user.empty:
                 role = df_user.iloc[0]['role']
                 st.session_state["role"] = role
        st.session_state["permissions"] = get_user_permissions_from_db(role)

    # 3. Executa a verificação
    page_name = os.path.splitext(os.path.basename(__file__))[0]
    
    # O perfil Master sempre tem acesso
    if st.session_state.get("role") == "Master":
        return
        
    allowed_pages = st.session_state.get("permissions", [])
    if page_name not in allowed_pages:
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()

check_permission()
# --- FIM DO BLOCO ---

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Visualização de Tabelas",
    page_icon="📚",
    layout="wide"
)

st.title("📚 Visualização das Tabelas do Banco de Dados")
st.write("Aqui você pode visualizar e filtrar os dados de cada tabela importada.")

# --- BOTÃO DE ATUALIZAÇÃO ---
if st.button("🔄 Atualizar Dados"):
    st.cache_data.clear()
    st.success("Dados atualizados com sucesso!")

st.markdown("---")

# --- CONEXÃO COM O BANCO DE DADOS ---
DB_FILE = "gestor_mkt.db"

@st.cache_data(ttl=600)
def carregar_dados(nome_tabela):
    """
    Função para carregar dados de uma tabela específica do banco de dados.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        query = f"SELECT * FROM {nome_tabela}"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar a tabela '{nome_tabela}': {e}")
        return pd.DataFrame()

# --- LISTA DE TABELAS PARA EXIBIR (COM A NOVA TABELA 'produtos') ---
tabelas = {
    "Clientes": "clientes",
    "Produtos": "produtos", # <-- ADICIONADO AQUI
    "Suri": "suri",
    "RD Station": "rd",
    "Vendas": "vendas",
    "Pedidos": "pedidos",
    "Tags": "tag"
}

# --- CRIA UM EXPANDER PARA CADA TABELA ---
for nome_amigavel, nome_tabela in tabelas.items():
    with st.expander(f"Visualizar Tabela: {nome_amigavel}", expanded=False):
        df_tabela = carregar_dados(nome_tabela)
        
        if not df_tabela.empty:
            
            filtro_texto = st.text_input(
                f"Filtrar em '{nome_amigavel}'", 
                key=f"filtro_{nome_tabela}"
            )
            
            df_filtrado = df_tabela.copy()
            if filtro_texto:
                df_str = df_tabela.astype(str)
                mascara = np.column_stack([
                    df_str[col].str.contains(filtro_texto, case=False, na=False) 
                    for col in df_str.columns
                ]).any(axis=1)
                df_filtrado = df_tabela[mascara]

            st.write(f"Exibindo {len(df_filtrado)} de {len(df_tabela)} registros.")
            
            st.dataframe(df_filtrado, width='stretch', hide_index=True)
            
        else:
            st.warning(f"A tabela '{nome_tabela}' está vazia ou não foi encontrada. "
                       "Verifique se o upload correspondente foi realizado.")