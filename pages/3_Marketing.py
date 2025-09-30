import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
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
st.set_page_config(page_title="Dashboard de Marketing", page_icon="🚀", layout="wide")
st.title("Dashboard de Marketing e Vendas")
if st.button("Atualizar Dados", icon="🔄"):
    st.cache_data.clear()
    st.toast("Dados do dashboard atualizados!", icon="✅")
st.markdown("---")

# --- CONEXÃO COM O BANCO DE DADOS ---
DB_FILE = "gestor_mkt.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)

# --- FUNÇÕES DE APOIO E FORMATAÇÃO ---
def formatar_valor(valor, is_currency=False):
    prefixo = "R$ " if is_currency else ""
    return prefixo + f"{valor:,.0f}".replace(",", ".")

@st.cache_data(ttl=600)
def get_anos_disponiveis(_conexao, empresa_id):
    filtro_empresa_vendas = f"WHERE Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    filtro_empresa_pedidos = f"WHERE Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query_vendas = f"SELECT DISTINCT strftime('%Y', substr(Data_NF, 7, 4) || '-' || substr(Data_NF, 4, 2) || '-' || substr(Data_NF, 1, 2)) as ano FROM vendas {filtro_empresa_vendas}"
    query_pedidos = f"SELECT DISTINCT strftime('%Y', substr(Dt_Entrega, 7, 4) || '-' || substr(Dt_Entrega, 4, 2) || '-' || substr(Dt_Entrega, 1, 2)) as ano FROM pedidos {filtro_empresa_pedidos}"
    try:
        df_vendas = pd.read_sql_query(query_vendas, _conexao)
        df_pedidos = pd.read_sql_query(query_pedidos, _conexao)
        anos = pd.concat([df_vendas['ano'], df_pedidos['ano']]).dropna().unique()
        anos.sort()
        return anos if len(anos) > 0 else [str(datetime.now().year)]
    except: return [str(datetime.now().year)]

# --- BARRA LATERAL DE FILTROS ---
st.sidebar.header("Filtros")
empresas_map = {"Todos": "Todos", "Distribuidora": "1", "Loja": "3"}
empresa_selecionada_nome = st.sidebar.selectbox("Empresa", list(empresas_map.keys()))
empresa_selecionada_id = empresas_map[empresa_selecionada_nome]
agora = datetime.now()
ano_atual = str(agora.year)
mes_atual_num = agora.month
anos_disponiveis = get_anos_disponiveis(conn, empresa_selecionada_id)
indice_ano_atual = list(anos_disponiveis).index(ano_atual) if ano_atual in anos_disponiveis else 0
ano_selecionado = st.sidebar.selectbox("Ano", anos_disponiveis, index=indice_ano_atual)
meses_pt = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
meses_selecionados_nomes = st.sidebar.multiselect("Selecione o(s) Mês(es)", options=list(meses_pt.values()), default=[meses_pt[mes_atual_num]])
meses_selecionados_nums = [k for k, v in meses_pt.items() if v in meses_selecionados_nomes]

# --- LÓGICA DE FILTRAGEM ---
def construir_clausula_where(coluna_data, ano, meses_nums):
    if not meses_nums: return "1=0"
    clausula_ano = f"strftime('%Y', substr({coluna_data}, 7, 4) || '-' || substr({coluna_data}, 4, 2) || '-' || substr({coluna_data}, 1, 2)) = '{ano}'"
    lista_meses_formatada = [f"'{str(m).zfill(2)}'" for m in meses_nums]
    clausula_meses = f"strftime('%m', substr({coluna_data}, 7, 4) || '-' || substr({coluna_data}, 4, 2) || '-' || substr({coluna_data}, 1, 2)) IN ({', '.join(lista_meses_formatada)})"
    return f"{clausula_ano} AND {clausula_meses}"

def clausula_clientes_novos(nome_coluna_codigo):
    return f"((CAST({nome_coluna_codigo} AS INTEGER) > 3820 AND CAST({nome_coluna_codigo} AS INTEGER) <= 4000) OR (CAST({nome_coluna_codigo} AS INTEGER) >= 880660003 AND CAST({nome_coluna_codigo} AS INTEGER) <= 980660003))"

clausula_tags_sdr_join = "(c.Tags LIKE '%#673AB1%' OR c.Tags LIKE '%#673AB2%' OR c.Tags LIKE '%#673AB3%' OR c.Tags LIKE '%#673AB4%' OR c.Tags LIKE '%#673AB5%' OR c.Tags LIKE '%#673AB6%' OR c.Tags LIKE '%#673AB7%')"
clausula_tags_sdr_clientes = clausula_tags_sdr_join.replace("c.", "")

# --- FUNÇÕES DE CONSULTA (Queries) ---
# SDR
def get_sdr_total_clientes(conexao):
    query = f"SELECT COUNT(Codigo) FROM clientes WHERE {clausula_tags_sdr_clientes};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_sdr_clientes_qualificados(conexao):
    query = "SELECT COUNT(Codigo) FROM clientes WHERE Tags = '#673AB4';"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_sdr_total_vendas(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT SUM(v.Valor_Total) FROM clientes c JOIN vendas v ON c.Codigo = v.Codcli WHERE {clausula_tags_sdr_join} AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0.0
def get_sdr_total_pedidos(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('p.Dt_Entrega', ano, meses)
    filtro_empresa = f"AND p.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT SUM(p.Vlr_Liquido) FROM clientes c JOIN pedidos p ON c.Codigo = p.Codcli WHERE {clausula_tags_sdr_join} AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0.0
def get_sdr_clientes_novos(conexao):
    query = f"SELECT COUNT(Codigo) FROM clientes WHERE {clausula_tags_sdr_clientes} AND {clausula_clientes_novos('Codigo')};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_sdr_novos_compradores(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT COUNT(DISTINCT c.Codigo) FROM clientes c JOIN vendas v ON c.Codigo = v.Codcli WHERE {clausula_tags_sdr_join} AND {clausula_clientes_novos('c.Codigo')} AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_sdr_clientes_reativados(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT COUNT(DISTINCT c.Codigo) FROM clientes c JOIN vendas v ON c.Codigo = v.Codcli WHERE c.Tags LIKE '%#673AB4%' AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
@st.cache_data(ttl=600)
def get_sdr_clientes_por_tag(_conexao):
    query = "SELECT t.tag_nome, COUNT(c.Codigo) as total FROM clientes c JOIN tag t ON c.Tags LIKE '%' || t.tag_id || '%' GROUP BY t.tag_nome ORDER BY total DESC;"
    df = pd.read_sql_query(query, _conexao).rename(columns={'tag_nome': 'Tag', 'total': 'Total de Clientes'})
    return df

# SURI
def get_suri_numeros_distintos(conexao, ano, meses):
    clausula_where_data = construir_clausula_where('Primeiro_Contato', ano, meses)
    query = f"SELECT COUNT(DISTINCT Numero) FROM suri WHERE {clausula_where_data};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_suri_clientes_distintos(conexao, ano, meses):
    clausula_where_data = construir_clausula_where('Primeiro_Contato', ano, meses)
    query = f"SELECT COUNT(DISTINCT codcli) FROM suri WHERE codcli != '0' AND {clausula_where_data};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_suri_total_vendas(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT SUM(v.Valor_Total) FROM suri s JOIN vendas v ON s.codcli = v.Codcli WHERE s.codcli != '0' AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0.0
def get_suri_total_pedidos(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('p.Dt_Entrega', ano, meses)
    filtro_empresa = f"AND p.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT SUM(p.Qt_Vend * p.Vlr_Unit) FROM suri s JOIN pedidos p ON s.codcli = p.Codcli WHERE s.codcli != '0' AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0.0
def get_suri_clientes_novos(conexao):
    query = f"SELECT COUNT(DISTINCT codcli) FROM suri WHERE codcli != '0' AND {clausula_clientes_novos('codcli')};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_suri_novos_compradores(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT COUNT(DISTINCT s.codcli) FROM suri s JOIN vendas v ON s.codcli = v.Codcli WHERE s.codcli != '0' AND {clausula_clientes_novos('s.codcli')} AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_suri_clientes_reativados(conexao, ano, meses, empresa_id):
    if not meses: return 0
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    data_inicio_periodo = datetime(int(ano), min(meses), 1)
    data_fim_anterior = data_inicio_periodo - relativedelta(days=1)
    data_inicio_anterior = data_fim_anterior - relativedelta(months=3) + relativedelta(days=1)
    clausula_where_anterior = f"strftime('%Y-%m-%d', substr(Data_NF, 7, 4) || '-' || substr(Data_NF, 4, 2) || '-' || substr(Data_NF, 1, 2)) BETWEEN '{data_inicio_anterior.strftime('%Y-%m-%d')}' AND '{data_fim_anterior.strftime('%Y-%m-%d')}'"
    query_anterior = f"SELECT DISTINCT v.Codcli FROM vendas v JOIN suri s ON v.Codcli = s.codcli WHERE s.codcli != '0' AND {clausula_where_anterior} {filtro_empresa};"
    clientes_periodo_anterior = pd.read_sql_query(query_anterior, conexao)['Codcli'].tolist()
    clausula_where_atual = construir_clausula_where('v.Data_NF', ano, meses)
    query_atual = f"SELECT DISTINCT v.Codcli FROM vendas v JOIN suri s ON v.Codcli = s.codcli WHERE s.codcli != '0' AND {clausula_where_atual} {filtro_empresa};"
    clientes_periodo_atual = pd.read_sql_query(query_atual, conexao)['Codcli'].tolist()
    reativados = [c for c in clientes_periodo_atual if c not in clientes_periodo_anterior]
    return len(reativados)
@st.cache_data(ttl=600)
def get_suri_top_clientes(_conexao, ano, meses, empresa_id):
    if not meses: return pd.DataFrame()
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    # --- CORREÇÃO AQUI: Usa c.Estado em vez de c.UF ---
    query = f"""
        SELECT c.Nome, c.Estado, SUM(v.Valor_Total) as Valor_Total 
        FROM suri s 
        JOIN vendas v ON s.codcli = v.Codcli 
        JOIN clientes c ON s.codcli = c.Codigo 
        WHERE s.codcli != '0' AND {clausula_where_data} {filtro_empresa} 
        GROUP BY c.Nome, c.Estado 
        ORDER BY Valor_Total DESC 
        LIMIT 10;
    """
    df = pd.read_sql_query(query, _conexao).rename(columns={'Nome': 'Cliente', 'Estado': 'UF', 'Valor_Total': 'Valor Total (R$)'})
    return df

# RD MARKETING
def get_rd_numeros_distintos(conexao, ano, meses):
    clausula_where_data = construir_clausula_where('Data_ultima_conversao', ano, meses)
    query = f"SELECT COUNT(DISTINCT Celular) FROM rd WHERE {clausula_where_data};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_rd_clientes_distintos(conexao, ano, meses):
    clausula_where_data = construir_clausula_where('Data_ultima_conversao', ano, meses)
    query = f"SELECT COUNT(DISTINCT CodigoCliente) FROM rd WHERE CodigoCliente IS NOT NULL AND CodigoCliente != '' AND {clausula_where_data};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_rd_total_vendas(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT SUM(v.Valor_Total) FROM rd r JOIN vendas v ON r.CodigoCliente = v.Codcli WHERE r.CodigoCliente IS NOT NULL AND r.CodigoCliente != '' AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0.0
def get_rd_total_pedidos(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('p.Dt_Entrega', ano, meses)
    filtro_empresa = f"AND p.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT SUM(p.Vlr_Liquido) FROM rd r JOIN pedidos p ON r.CodigoCliente = p.Codcli WHERE r.CodigoCliente IS NOT NULL AND r.CodigoCliente != '' AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0.0
def get_rd_clientes_novos(conexao):
    query = f"SELECT COUNT(DISTINCT CodigoCliente) FROM rd WHERE (CodigoCliente IS NOT NULL AND CodigoCliente != '') AND {clausula_clientes_novos('CodigoCliente')};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_rd_novos_compradores(conexao, ano, meses, empresa_id):
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query = f"SELECT COUNT(DISTINCT r.CodigoCliente) FROM rd r JOIN vendas v ON r.CodigoCliente = v.Codcli WHERE (r.CodigoCliente IS NOT NULL AND r.CodigoCliente != '') AND {clausula_clientes_novos('r.CodigoCliente')} AND {clausula_where_data} {filtro_empresa};"
    return pd.read_sql_query(query, conexao).iloc[0, 0] or 0
def get_rd_clientes_reativados(conexao, ano, meses, empresa_id):
    if not meses: return 0
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    data_inicio_periodo = datetime(int(ano), min(meses), 1)
    data_fim_anterior = data_inicio_periodo - relativedelta(days=1)
    data_inicio_anterior = data_fim_anterior - relativedelta(months=3) + relativedelta(days=1)
    clausula_where_anterior = f"strftime('%Y-%m-%d', substr(Data_NF, 7, 4) || '-' || substr(Data_NF, 4, 2) || '-' || substr(Data_NF, 1, 2)) BETWEEN '{data_inicio_anterior.strftime('%Y-%m-%d')}' AND '{data_fim_anterior.strftime('%Y-%m-%d')}'"
    query_anterior = f"SELECT DISTINCT v.Codcli FROM vendas v JOIN rd r ON v.Codcli = r.CodigoCliente WHERE r.CodigoCliente IS NOT NULL AND {clausula_where_anterior} {filtro_empresa};"
    clientes_periodo_anterior = pd.read_sql_query(query_anterior, conexao)['Codcli'].tolist()
    clausula_where_atual = construir_clausula_where('v.Data_NF', ano, meses)
    query_atual = f"SELECT DISTINCT v.Codcli FROM vendas v JOIN rd r ON v.Codcli = r.CodigoCliente WHERE r.CodigoCliente IS NOT NULL AND {clausula_where_atual} {filtro_empresa};"
    clientes_periodo_atual = pd.read_sql_query(query_atual, conexao)['Codcli'].tolist()
    reativados = [c for c in clientes_periodo_atual if c not in clientes_periodo_anterior]
    return len(reativados)
@st.cache_data(ttl=600)
def get_rd_top_clientes(_conexao, ano, meses, empresa_id):
    if not meses: return pd.DataFrame()
    clausula_where_data = construir_clausula_where('v.Data_NF', ano, meses)
    filtro_empresa = f"AND v.Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    # --- CORREÇÃO AQUI: Usa c.Estado em vez de c.UF ---
    query = f"""
        SELECT c.Nome, c.Estado, SUM(v.Valor_Total) as Valor_Total 
        FROM rd r 
        JOIN vendas v ON r.CodigoCliente = v.Codcli 
        JOIN clientes c ON r.CodigoCliente = c.Codigo 
        WHERE r.CodigoCliente IS NOT NULL AND {clausula_where_data} {filtro_empresa} 
        GROUP BY c.Nome, c.Estado 
        ORDER BY Valor_Total DESC 
        LIMIT 10;
    """
    df = pd.read_sql_query(query, _conexao).rename(columns={'Nome': 'Cliente', 'Estado': 'UF', 'Valor_Total': 'Valor Total (R$)'})
    return df

# --- RENDERIZAÇÃO DO DASHBOARD ---
col1, col2, col3 = st.columns(3)
with col1:
    with st.container(border=True):
        st.markdown("### 📋 SDR")
        total_vendas_sdr = get_sdr_total_vendas(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        total_pedidos_sdr = get_sdr_total_pedidos(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        novos_compradores_sdr = get_sdr_novos_compradores(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        clientes_reativados_sdr = get_sdr_clientes_reativados(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        total_clientes_sdr = get_sdr_total_clientes(conn)
        clientes_qualificados_sdr = get_sdr_clientes_qualificados(conn)
        clientes_novos_sdr = get_sdr_clientes_novos(conn)
        st.metric(label="Clientes Direcionados (com Tag)", value=formatar_valor(total_clientes_sdr))
        st.metric(label="Clientes Qualificados", value=formatar_valor(clientes_qualificados_sdr))
        st.metric(label="Total de Vendas", value=formatar_valor(total_vendas_sdr, is_currency=True))
        st.metric(label="Total em Pedidos", value=formatar_valor(total_pedidos_sdr, is_currency=True))
        st.metric(label="Clientes Novos (Potencial)", value=formatar_valor(clientes_novos_sdr))
        st.metric(label="Novos Compradores (Período)", value=formatar_valor(novos_compradores_sdr))
        st.metric(label="Clientes Reativados", value=formatar_valor(clientes_reativados_sdr))
        st.markdown("---")
        st.markdown("##### Clientes por Tag")
        df_tags = get_sdr_clientes_por_tag(conn)
        st.dataframe(df_tags, width='stretch', hide_index=True)

with col2:
    with st.container(border=True):
        st.markdown("### 💬 Suri")
        numeros_distintos = get_suri_numeros_distintos(conn, ano_selecionado, meses_selecionados_nums)
        clientes_distintos = get_suri_clientes_distintos(conn, ano_selecionado, meses_selecionados_nums)
        total_vendas_suri = get_suri_total_vendas(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        total_pedidos_suri = get_suri_total_pedidos(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        clientes_novos_suri = get_suri_clientes_novos(conn)
        novos_compradores_suri = get_suri_novos_compradores(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        clientes_reativados_suri = get_suri_clientes_reativados(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        st.metric(label="Atendimentos (números distintos)", value=formatar_valor(numeros_distintos))
        st.metric(label="Clientes Atendidos (codcli ≠ 0)", value=formatar_valor(clientes_distintos))
        st.metric(label="Total de Vendas", value=formatar_valor(total_vendas_suri, is_currency=True))
        st.metric(label="Total em Pedidos", value=formatar_valor(total_pedidos_suri, is_currency=True))
        st.metric(label="Clientes Novos (Potencial)", value=formatar_valor(clientes_novos_suri))
        st.metric(label="Novos Compradores (Período)", value=formatar_valor(novos_compradores_suri))
        st.metric(label="Clientes Reativados", value=formatar_valor(clientes_reativados_suri))
        st.markdown("---")
        st.markdown("##### Top 10 Clientes (Vendas)")
        df_top_clientes = get_suri_top_clientes(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        st.dataframe(df_top_clientes, width='stretch', hide_index=True, column_config={"Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.0f")})

with col3:
    with st.container(border=True):
        st.markdown("### 📈 RD Marketing")
        numeros_distintos_rd = get_rd_numeros_distintos(conn, ano_selecionado, meses_selecionados_nums)
        clientes_distintos_rd = get_rd_clientes_distintos(conn, ano_selecionado, meses_selecionados_nums)
        total_vendas_rd = get_rd_total_vendas(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        total_pedidos_rd = get_rd_total_pedidos(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        clientes_novos_rd = get_rd_clientes_novos(conn)
        novos_compradores_rd = get_rd_novos_compradores(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        clientes_reativados_rd = get_rd_clientes_reativados(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        st.metric(label="Atendimentos (números distintos)", value=formatar_valor(numeros_distintos_rd))
        st.metric(label="Clientes Atendidos (codcli ≠ 0)", value=formatar_valor(clientes_distintos_rd))
        st.metric(label="Total de Vendas", value=formatar_valor(total_vendas_rd, is_currency=True))
        st.metric(label="Total em Pedidos", value=formatar_valor(total_pedidos_rd, is_currency=True))
        st.metric(label="Clientes Novos (Potencial)", value=formatar_valor(clientes_novos_rd))
        st.metric(label="Novos Compradores (Período)", value=formatar_valor(novos_compradores_rd))
        st.metric(label="Clientes Reativados", value=formatar_valor(clientes_reativados_rd))
        st.markdown("---")
        st.markdown("##### Top 10 Clientes (Vendas)")
        df_top_clientes_rd = get_rd_top_clientes(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id)
        st.dataframe(df_top_clientes_rd, width='stretch', hide_index=True, column_config={"Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.0f")})

conn.close()