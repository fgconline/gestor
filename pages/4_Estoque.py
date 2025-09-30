import streamlit as st
import pandas as pd
import sqlite3
import os

# --- BLOCO DE CONTROLE DE ACESSO ---
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
    page_name = os.path.splitext(os.path.basename(__file__))[0]
    if st.session_state.get("role") == "Master": return
    if "permissions" not in st.session_state or st.session_state.permissions is None:
        st.session_state["permissions"] = get_user_permissions_from_db(st.session_state.get("role"))
    if page_name not in st.session_state.get("permissions", []):
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()
check_permission()
# --- FIM DO BLOCO ---

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Estoque", page_icon="📦", layout="wide")
st.title("📦 Análise de Estoque")

if st.button("🔄 Atualizar Dados"):
    st.cache_data.clear()
    st.toast("Dados de estoque atualizados!", icon="✅")
    st.rerun()
st.markdown("---")

# --- FUNÇÕES E CARREGAMENTO DE DADOS ---
DB_FILE = "gestor_mkt.db"

@st.cache_data(ttl=600)
def carregar_dados_estoque():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        query = """
            SELECT 
                e.codpro, 
                e.produto, 
                e.qtde, 
                e.deposito, 
                p.m2 
            FROM estoque e
            LEFT JOIN produtos p ON e.codpro = p.codpro
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        df['qtde'] = pd.to_numeric(df['qtde'], errors='coerce').fillna(0)
        df['m2'] = pd.to_numeric(df['m2'], errors='coerce')
        df['rolos'] = df.apply(lambda row: row['qtde'] / row['m2'] if pd.notna(row['m2']) and row['m2'] > 0 else 0, axis=1)
        
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados de estoque: {e}")
        return pd.DataFrame()

df_estoque = carregar_dados_estoque()

if df_estoque.empty:
    st.warning("Nenhum dado de estoque encontrado. Por favor, importe os arquivos de estoque na página de 'Uploads'.")
else:
    unidade = st.radio("Visualizar estoque em:", ["M²", "Rolos"], horizontal=True)
    coluna_valor = 'qtde' if unidade == "M²" else 'rolos'

    # --- CARDS DE TOTAIS ---
    st.markdown("##### Totais por Depósito")
    depositos = sorted(df_estoque['deposito'].unique())
    cols = st.columns(len(depositos) + 1)
    
    total_geral = 0
    for i, dep in enumerate(depositos):
        with cols[i]:
            with st.container(border=True):
                total_dep = df_estoque[df_estoque['deposito'] == dep][coluna_valor].sum()
                st.metric(label=f"Total {dep.upper()}", value=f"{total_dep:,.0f}".replace(',', '.'))
                total_geral += total_dep
    
    with cols[-1]:
        with st.container(border=True):
            st.metric(label="TOTAL GERAL", value=f"{total_geral:,.0f}".replace(',', '.'))
            
    st.markdown("---")
    
    # --- TABELA DETALHADA ---
    st.markdown("##### Estoque por Produto")
    
    pivot_table = pd.pivot_table(
        df_estoque,
        values=coluna_valor,
        index=['codpro', 'produto'],
        columns=['deposito'],
        aggfunc='sum',
        fill_value=0
    )

    pivot_table['Total'] = pivot_table.sum(axis=1)
    pivot_table = pivot_table.sort_values(by='Total', ascending=False).reset_index()

    # --- CAMPO DE PESQUISA (NOVO) ---
    pesquisa = st.text_input(
        "Pesquisar na tabela (separe os termos por vírgula):",
        key="pesquisa_estoque"
    )

    df_para_exibir = pivot_table.copy()
    if pesquisa:
        termos = [term.strip().lower() for term in pesquisa.split(',') if term.strip()]
        df_str = df_para_exibir.astype(str).apply(lambda x: x.str.lower())
        
        for termo in termos:
            # Mantém apenas as linhas que contêm o termo em qualquer coluna
            df_para_exibir = df_para_exibir[df_str.apply(lambda row: row.str.contains(termo, na=False)).any(axis=1)]
            # Recalcula o df_str para a próxima iteração do filtro
            if not df_para_exibir.empty:
                 df_str = df_para_exibir.astype(str).apply(lambda x: x.str.lower())
            else:
                 break
    
    st.write(f"Exibindo **{len(df_para_exibir)}** de **{len(pivot_table)}** produtos.")

    # Formatação para o display (CORRIGIDO)
    colunas_numericas = [c for c in df_para_exibir.columns if c not in ['codpro', 'produto']]
    formatter = lambda x: f'{x:,.0f}'.replace(',', '.')

    st.dataframe(
        df_para_exibir.style.format(formatter, subset=colunas_numericas)
                           .set_properties(**{'text-align': 'right'}, subset=colunas_numericas),
        width='stretch',
        hide_index=True
    )