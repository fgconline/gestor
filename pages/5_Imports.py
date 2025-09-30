import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

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
st.set_page_config(page_title="Importações", page_icon="🚢", layout="wide")
st.title("🚢 Análise de Importações")

if st.button("🔄 Atualizar Dados"):
    st.cache_data.clear()
    st.toast("Dados de importação atualizados!", icon="✅")
    st.rerun()
st.markdown("---")

# --- FUNÇÕES E CARREGAMENTO DE DADOS ---
DB_FILE = "gestor_mkt.db"

def formatar_valor(valor, decimais=0):
    if pd.isna(valor): return ""
    return f"{valor:,.{decimais}f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data(ttl=600)
def carregar_dados_imports():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        df = pd.read_sql_query("SELECT * FROM imports", conn)
        conn.close()
        
        df['Data_prevista'] = pd.to_datetime(df['Data_prevista'], format='%d/%m/%Y', errors='coerce')
        df['Ano'] = df['Data_prevista'].dt.year.astype('Int64').astype(str)
        df['Mes'] = df['Data_prevista'].dt.month.astype('Int64').astype(str)
        
        # Converte colunas numéricas
        df['Rolos'] = pd.to_numeric(df['Rolos'], errors='coerce').fillna(0)
        df['M2'] = pd.to_numeric(df['M2'], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        return pd.DataFrame()

df_imports = carregar_dados_imports()

if df_imports.empty:
    st.warning("Nenhum dado de importação encontrado. Por favor, importe o arquivo 'imports.xlsx' na página de 'Uploads'.")
else:
    # --- BARRA LATERAL DE FILTROS COM DEFAULTS ---
    st.sidebar.header("Filtros de Importação")
    
    agora = datetime.now()
    ano_atual_str = str(agora.year)
    mes_atual_num = agora.month

    anos = sorted(df_imports['Ano'].dropna().unique(), reverse=True)
    ano_selecionado = st.sidebar.selectbox("Ano", anos, index=anos.index(ano_atual_str) if ano_atual_str in anos else 0)

    df_ano_filtrado = df_imports[df_imports['Ano'] == ano_selecionado]

    meses_pt = {"1": "Janeiro", "2": "Fevereiro", "3": "Março", "4": "Abril", "5": "Maio", "6": "Junho", "7": "Julho", "8": "Agosto", "9": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro"}
    meses_disponiveis = sorted(df_ano_filtrado['Mes'].dropna().unique(), key=int)
    
    meses_default_nums = [m for m in meses_disponiveis if int(m) >= mes_atual_num]
    meses_default_nomes = [meses_pt[m] for m in meses_default_nums]
    
    meses_nomes_disponiveis = [meses_pt[m] for m in meses_disponiveis]
    meses_selecionados_nomes = st.sidebar.multiselect("Mês(es)", meses_nomes_disponiveis, default=meses_default_nomes)
    meses_selecionados_nums = [k for k, v in meses_pt.items() if v in meses_selecionados_nomes]

    status_fabrica = sorted(df_imports['Status_fabrica'].dropna().unique())
    status_default = [s for s in ['ATENDIDO', 'ATENDIDO BACKORDER'] if s in status_fabrica]
    status_selecionados = st.sidebar.multiselect("Status da Fábrica", status_fabrica, default=status_default)

    recebido = sorted(df_imports['Recebido'].dropna().unique())
    recebido_default = ['não'] if 'não' in recebido else []
    recebido_selecionados = st.sidebar.multiselect("Status Recebido", recebido, default=recebido_default)

    if 'reservado' in df_imports.columns:
        reservado = sorted(df_imports['reservado'].dropna().unique())
        reservado_default = ['não'] if 'não' in reservado else []
        reservado_selecionados = st.sidebar.multiselect("Reservado", reservado, default=reservado_default)
    else:
        reservado_selecionados = []

    # --- APLICAÇÃO DOS FILTROS DA BARRA LATERAL ---
    df_filtrado = df_imports.copy()
    if ano_selecionado:
        df_filtrado = df_filtrado[df_filtrado['Ano'] == ano_selecionado]
    if meses_selecionados_nums:
        df_filtrado = df_filtrado[df_filtrado['Mes'].isin(meses_selecionados_nums)]
    if status_selecionados:
        df_filtrado = df_filtrado[df_filtrado['Status_fabrica'].isin(status_selecionados)]
    if recebido_selecionados:
        df_filtrado = df_filtrado[df_filtrado['Recebido'].isin(recebido_selecionados)]
    if 'reservado' in df_filtrado.columns and reservado_selecionados:
        df_filtrado = df_filtrado[df_filtrado['reservado'].isin(reservado_selecionados)]

    # --- CAMPO DE PESQUISA (NOVO) ---
    pesquisa = st.text_input("Pesquisar na tabela (separe os termos por vírgula):")

    df_para_exibir = df_filtrado.copy()
    if pesquisa:
        termos = [term.strip().lower() for term in pesquisa.split(',') if term.strip()]
        df_str = df_para_exibir.astype(str).apply(lambda x: x.str.lower())
        
        for termo in termos:
            df_para_exibir = df_para_exibir[df_str.apply(lambda row: row.str.contains(termo, na=False)).any(axis=1)]
            if not df_para_exibir.empty:
                 df_str = df_para_exibir.astype(str).apply(lambda x: x.str.lower())
            else:
                 break
    
    # --- CARDS DE TOTAIS (NOVOS) ---
    st.markdown("##### Resumo da Seleção")
    total_itens = len(df_para_exibir)
    total_m2 = df_para_exibir['M2'].sum()
    total_rolos = df_para_exibir['Rolos'].sum()

    col1, col2, col3 = st.columns(3)
    with col1:
        with st.container(border=True):
            st.metric(label="Total de Itens", value=formatar_valor(total_itens))
    with col2:
        with st.container(border=True):
            st.metric(label="Total em M²", value=formatar_valor(total_m2))
    with col3:
        with st.container(border=True):
            st.metric(label="Total em Rolos", value=formatar_valor(total_rolos))
    
    st.markdown("---")

    # --- EXIBIÇÃO DA TABELA ---
    st.write(f"Exibindo **{len(df_para_exibir)}** de **{len(df_imports)}** registros.")
    
    # Formata a data de volta para string para exibição na tabela
    df_para_exibir['Data_prevista'] = df_para_exibir['Data_prevista'].dt.strftime('%d/%m/%Y')
    
    colunas_para_exibir = ['nome', 'Data_prevista', 'CodPro', 'Descricao', 'Rolos', 'M2', 'Status_fabrica', 'Recebido', 'reservado']
    colunas_numericas = ['Rolos', 'M2']
    
    formatter = lambda x: formatar_valor(x, decimais=0)

    st.dataframe(
        df_para_exibir[colunas_para_exibir].style.format(formatter, subset=colunas_numericas)
                                         .set_properties(**{'text-align': 'right'}, subset=colunas_numericas),
        width='stretch',
        hide_index=True
    )