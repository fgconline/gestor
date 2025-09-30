import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
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
    # 1. Se não estiver logado, redireciona para o login
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
# --- FIM DO NOVO BLOCO ---


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Análise de Vendas", page_icon="💰", layout="wide")
st.title("💰 Análise de Vendas")
st.markdown("---")

# --- CONEXÃO COM O BANCO DE DADOS E FUNÇÕES DE APOIO ---
DB_FILE = "gestor_mkt.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)

def formatar_valor(valor, is_currency=False, decimais=0):
    if pd.isna(valor) or not isinstance(valor, (int, float, complex)): return valor
    prefixo = "R$ " if is_currency else ""
    return prefixo + f"{valor:,.{decimais}f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data(ttl=600)
def get_dados_filtro(_conexao, empresa_id):
    filtro_empresa = f"WHERE Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query_anos = f"SELECT DISTINCT strftime('%Y', substr(Data_NF, 7, 4) || '-' || substr(Data_NF, 4, 2) || '-' || substr(Data_NF, 1, 2)) as ano FROM vendas {filtro_empresa}"
    query_vendedores = "SELECT codvend, vendedor_nome FROM vendedores ORDER BY vendedor_nome"
    try:
        df_anos = pd.read_sql_query(query_anos, _conexao)
        anos = df_anos['ano'].dropna().unique(); anos.sort()
        df_vendedores = pd.read_sql_query(query_vendedores, _conexao)
        vendedores_map = pd.Series(df_vendedores.codvend.values, index=df_vendedores.vendedor_nome).to_dict()
        return anos if len(anos) > 0 else [str(datetime.now().year)], vendedores_map
    except: 
        return [str(datetime.now().year)], {}

# --- BARRA LATERAL DE FILTROS ---
st.sidebar.header("Filtros")
empresas_map = {"Todos": "Todos", "Distribuidora": "1", "Loja": "3"}
empresa_selecionada_nome = st.sidebar.selectbox("Empresa", list(empresas_map.keys()), key="vendas_empresa")
empresa_selecionada_id = empresas_map[empresa_selecionada_nome]
anos_disponiveis, vendedores_map = get_dados_filtro(conn, empresa_selecionada_id)
agora = datetime.now()
ano_atual = str(agora.year)
mes_atual_num = agora.month
indice_ano_atual = list(anos_disponiveis).index(ano_atual) if ano_atual in anos_disponiveis else 0
ano_selecionado = st.sidebar.selectbox("Ano", anos_disponiveis, index=indice_ano_atual, key="vendas_ano")
meses_pt = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
meses_selecionados_nomes = st.sidebar.multiselect("Selecione o(s) Mês(es)", options=list(meses_pt.values()), default=[meses_pt[mes_atual_num]], key="vendas_mes")
meses_selecionados_nums = [k for k, v in meses_pt.items() if v in meses_selecionados_nomes]
vendedores_selecionados_nomes = st.sidebar.multiselect("Vendedor", options=list(vendedores_map.keys()), default=list(vendedores_map.keys()))
vendedores_selecionados_ids = [vendedores_map[nome] for nome in vendedores_selecionados_nomes]

# --- FUNÇÃO PRINCIPAL PARA CARREGAR DADOS ---
@st.cache_data(ttl=600)
def carregar_dados_vendas(_conexao, ano, meses, empresa, vendedores_ids):
    if not meses or not vendedores_ids: return pd.DataFrame()
    clausula_ano = f"strftime('%Y', substr(v.Data_NF, 7, 4) || '-' || substr(v.Data_NF, 4, 2) || '-' || substr(v.Data_NF, 1, 2)) = '{ano}'"
    lista_meses_formatada = [f"'{str(m).zfill(2)}'" for m in meses]
    clausula_meses = f"strftime('%m', substr(v.Data_NF, 7, 4) || '-' || substr(v.Data_NF, 4, 2) || '-' || substr(v.Data_NF, 1, 2)) IN ({', '.join(lista_meses_formatada)})"
    filtro_empresa = f"AND v.Empresa = '{empresa}'" if empresa != "Todos" else ""
    lista_vendedores_formatada = [f"'{str(v)}'" for v in vendedores_ids]
    filtro_vendedores = f"AND v.Vend IN ({','.join(lista_vendedores_formatada)})"
    query = f"SELECT v.*, p.descricao as Descricao_Produto, p.m2, COALESCE(vend.vendedor_nome, 'Inativo') as Nome_Vendedor FROM vendas v LEFT JOIN produtos p ON v.Codpro = p.codpro LEFT JOIN vendedores vend ON v.Vend = vend.codvend WHERE {clausula_ano} AND {clausula_meses} {filtro_empresa} {filtro_vendedores}"
    df = pd.read_sql_query(query, _conexao)
    if not df.empty:
        for col in ['Valor_Total', 'QtdeFaturada', 'm2']: df[col] = pd.to_numeric(df[col], errors='coerce')
        df['Rolos'] = df.apply(lambda row: row['QtdeFaturada'] / row['m2'] if row['m2'] and row['m2'] > 0 else 0, axis=1)
        df['Mes'] = pd.to_datetime(df['Data_NF'], format='%d/%m/%Y').dt.month.map(meses_pt)
    return df

df_base = carregar_dados_vendas(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id, vendedores_selecionados_ids)

# --- INICIALIZAÇÃO E LÓGICA DO FILTRO DE PESQUISA COM SESSION STATE ---
if 'pesquisa_vendas' not in st.session_state:
    st.session_state.pesquisa_vendas = ""

pesquisa = st.text_input("Pesquisar em todos os dados para detalhar:", value=st.session_state.pesquisa_vendas, key="pesquisa_vendas_input")
st.session_state.pesquisa_vendas = pesquisa

if st.button("Limpar Filtro da Pesquisa"):
    st.session_state.pesquisa_vendas = ""
    st.rerun()

df_para_visualizacao = df_base.copy()
if st.session_state.pesquisa_vendas:
    termo = st.session_state.pesquisa_vendas
    # Procura o termo em colunas relevantes
    cols_pesquisa = ['Nome_do_Cliente', 'UF', 'Descricao_Produto', 'Nome_Vendedor']
    df_para_visualizacao = df_base[df_base[cols_pesquisa].astype(str).apply(lambda x: x.str.contains(termo, case=False)).any(axis=1)]

# --- SEÇÃO PRINCIPAL ---
if not df_para_visualizacao.empty:
    col1_ctrl, col2_ctrl, col3_ctrl = st.columns([2, 2, 1.5])
    agrupar_por = col1_ctrl.radio("Visualizar por:", options=["Cliente", "UF", "Produto", "Vendedor"], horizontal=True)
    if agrupar_por == "Produto":
        mostrar_unidade = col2_ctrl.radio("Mostrar valor em:", options=["M2", "Rolos"], horizontal=True, key="unidade_produto")
        coluna_valores = "QtdeFaturada" if mostrar_unidade == "M2" else "Rolos"
        is_currency_view = False
    else:
        mostrar_valor = col2_ctrl.radio("Mostrar valor em:", options=["Valor (R$)", "Quantidade"], horizontal=True, key="valor_geral")
        if mostrar_valor == "Valor (R$)":
            coluna_valores = "Valor_Total"
            is_currency_view = True
        else:
            mostrar_unidade_qtd = col3_ctrl.radio("Unidade:", options=["M2", "Rolos"], horizontal=True, key="unidade_qtd")
            coluna_valores = "QtdeFaturada" if mostrar_unidade_qtd == "M2" else "Rolos"
            is_currency_view = False

    # --- CARDS DE TOTAIS (Refletem os dados filtrados) ---
    label_qtd_card = f"Total Quantidade ({'Rolos' if coluna_valores == 'Rolos' and not is_currency_view else 'm²'})"
    total_valor_card = df_para_visualizacao['Valor_Total'].sum()
    total_qtd_card = df_para_visualizacao['Rolos'].sum() if coluna_valores == 'Rolos' and not is_currency_view else df_para_visualizacao['QtdeFaturada'].sum()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container(border=True):
            st.metric(label="Total Clientes", value=formatar_valor(df_para_visualizacao['Codcli'].nunique()))
    with col2:
        with st.container(border=True):
            st.metric(label="Total Produtos", value=formatar_valor(df_para_visualizacao['Codpro'].nunique()))
    with col3:
        with st.container(border=True):
            st.metric(label=label_qtd_card, value=formatar_valor(total_qtd_card, decimais=0))
    with col4:
        with st.container(border=True):
            st.metric(label="Total Valor", value=formatar_valor(total_valor_card, is_currency=True))
    st.markdown("---")
    
    # --- LÓGICA DA TABELA DINÂMICA ---
    coluna_indice = {"Cliente": ["Nome_do_Cliente", "Nome_Vendedor"], "UF": "UF", "Produto": "Descricao_Produto", "Vendedor": "Nome_Vendedor"}[agrupar_por]
    ordem_meses = [meses_pt[i] for i in sorted(meses_selecionados_nums)]
    pivot_table = pd.pivot_table(df_para_visualizacao, values=coluna_valores, index=coluna_indice, columns='Mes', aggfunc='sum', fill_value=0).reindex(ordem_meses, axis=1, fill_value=0)
    pivot_table['Total'] = pivot_table[ordem_meses].sum(axis=1)
    
    num_meses = len(ordem_meses)
    pivot_table['Média'] = pivot_table['Total'] / num_meses if num_meses > 0 else 0
    pivot_table = pivot_table.sort_values(by='Total', ascending=False)
    
    pivot_table_display = pivot_table.reset_index()
    
    total_row = pivot_table_display[ordem_meses + ['Total', 'Média']].sum().to_dict()
    total_row[pivot_table_display.columns[0]] = 'Total'
    if isinstance(coluna_indice, list):
        for i in range(1, len(coluna_indice)): total_row[pivot_table_display.columns[i]] = ''
    
    pivot_table_display = pd.concat([pivot_table_display, pd.DataFrame([total_row])], ignore_index=True)

    if agrupar_por == "Cliente":
        final_cols = ["Nome_do_Cliente", "Nome_Vendedor"] + ordem_meses + ["Média", "Total"]
        pivot_table_display = pivot_table_display[final_cols]
    
    formatter = "{:,.0f}"
    prefixo = "R$ " if is_currency_view else ""
    format_dict = {col: (prefixo + formatter) for col in pivot_table_display.columns if col not in ['Nome_do_Cliente', 'Nome_Vendedor', 'UF', 'Descricao_Produto']}
    config_coluna_indice = {col: st.column_config.Column(width="large") for col in (coluna_indice if isinstance(coluna_indice, list) else [coluna_indice])}
    
    st.dataframe(
    pivot_table_display.style.format(format_dict, na_rep="-").set_properties(**{'text-align': 'right'}),
    width='stretch',
    column_config=config_coluna_indice,
    hide_index=True
)
else:
    st.warning("Nenhum dado de venda encontrado para os filtros selecionados.")

conn.close()