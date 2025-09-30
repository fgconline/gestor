import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import numpy as np

# --- BLOCO DE CONTROLE DE ACESSO (Obrigatório em todas as páginas) ---
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
    if "permissions" not in st.session_state or st.session_state.permissions is None:
        role = st.session_state.get("role")
        if not role:
            conn = sqlite3.connect("gestor_mkt.db", check_same_thread=False)
            username = st.session_state.get("username")
            df_user = pd.read_sql_query(f"SELECT role FROM usuarios WHERE username = '{username}'", conn)
            conn.close()
            if not df_user.empty:
                role = df_user.iloc[0]['role']
                st.session_state["role"] = role
        st.session_state["permissions"] = get_user_permissions_from_db(role)
    page_name = os.path.splitext(os.path.basename(__file__))[0]
    if st.session_state.get("role") == "Master":
        return
    allowed_pages = st.session_state.get("permissions", [])
    if page_name not in allowed_pages:
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()
check_permission()
# --- FIM DO BLOCO ---


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Análise de Pedidos", page_icon="📦", layout="wide")
st.title("📦 Análise de Pedidos")
st.markdown("---")


# --- CONEXÃO COM O BANCO DE DADOS E FUNÇÕES DE APOIO ---
DB_FILE = "gestor_mkt.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)

def formatar_valor(valor, is_currency=False, decimais=0):
    if pd.isna(valor) or not isinstance(valor, (int, float, complex)): return valor
    prefixo = "R$ " if is_currency else ""
    return prefixo + f"{valor:,.{decimais}f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data(ttl=600)
def get_dados_filtro_pedidos(_conexao, empresa_id):
    filtro_empresa = f"WHERE Empresa = '{empresa_id}'" if empresa_id != "Todos" else ""
    query_anos = f"SELECT DISTINCT strftime('%Y', substr(Dt_Entrega, 7, 4) || '-' || substr(Dt_Entrega, 4, 2) || '-' || substr(Dt_Entrega, 1, 2)) as ano FROM pedidos {filtro_empresa}"
    query_vendedores = f"SELECT DISTINCT Cod_Vend, Nome_Vend FROM pedidos {filtro_empresa} ORDER BY Nome_Vend"
    try:
        df_anos = pd.read_sql_query(query_anos, _conexao)
        anos = df_anos['ano'].dropna().unique(); anos.sort()
        df_vendedores = pd.read_sql_query(query_vendedores, _conexao)
        vendedores_map = pd.Series(df_vendedores.Cod_Vend.values, index=df_vendedores.Nome_Vend).to_dict()
        return anos if len(anos) > 0 else [str(datetime.now().year)], vendedores_map
    except:
        return [str(datetime.now().year)], {}


# --- BARRA LATERAL DE FILTROS ---
st.sidebar.header("Filtros de Pedidos")
empresas_map = {"Todos": "Todos", "CD": "1", "Loja": "3"}
empresa_selecionada_nome = st.sidebar.selectbox("Empresa", list(empresas_map.keys()), key="pedidos_empresa")
empresa_selecionada_id = empresas_map[empresa_selecionada_nome]

anos_disponiveis, vendedores_map = get_dados_filtro_pedidos(conn, empresa_selecionada_id)
agora = datetime.now()
ano_atual = str(agora.year)
mes_atual_num = agora.month

indice_ano_atual = list(anos_disponiveis).index(ano_atual) if ano_atual in anos_disponiveis else 0
ano_selecionado = st.sidebar.selectbox("Ano", anos_disponiveis, index=indice_ano_atual, key="pedidos_ano")
meses_pt = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
meses_selecionados_nomes = st.sidebar.multiselect("Mês(es) da Entrega", options=list(meses_pt.values()), default=[meses_pt[mes_atual_num]], key="pedidos_mes")
meses_selecionados_nums = [k for k, v in meses_pt.items() if v in meses_selecionados_nomes]

tipos_map = {"Pedido": "P", "Cotação": "C"}
tipos_selecionados_nomes = st.sidebar.multiselect("Tipo", options=list(tipos_map.keys()), default=list(tipos_map.keys()))
tipos_selecionados_ids = [tipos_map[nome] for nome in tipos_selecionados_nomes]

vendedores_selecionados_nomes = st.sidebar.multiselect("Vendedor", options=list(vendedores_map.keys()), default=list(vendedores_map.keys()), key="pedidos_vendedor")
vendedores_selecionados_ids = [vendedores_map[nome] for nome in vendedores_selecionados_nomes]


# --- FUNÇÃO PRINCIPAL PARA CARREGAR DADOS ---
@st.cache_data(ttl=600)
def carregar_dados_pedidos(_conexao, ano, meses, empresa, vendedores_ids, tipos_ids):
    if not all([meses, vendedores_ids, tipos_ids]): return pd.DataFrame()

    clausula_ano = f"strftime('%Y', substr(p.Dt_Entrega, 7, 4) || '-' || substr(p.Dt_Entrega, 4, 2) || '-' || substr(p.Dt_Entrega, 1, 2)) = '{ano}'"
    lista_meses_formatada = [f"'{str(m).zfill(2)}'" for m in meses]
    clausula_meses = f"strftime('%m', substr(p.Dt_Entrega, 7, 4) || '-' || substr(p.Dt_Entrega, 4, 2) || '-' || substr(p.Dt_Entrega, 1, 2)) IN ({', '.join(lista_meses_formatada)})"

    filtro_empresa = f"AND p.Empresa = '{empresa}'" if empresa != "Todos" else ""
    lista_vendedores_formatada = [f"'{str(v)}'" for v in vendedores_ids]
    filtro_vendedores = f"AND p.Cod_Vend IN ({','.join(lista_vendedores_formatada)})"
    lista_tipos_formatada = [f"'{t}'" for t in tipos_ids]
    filtro_tipo = f"AND p.Tipo IN ({','.join(lista_tipos_formatada)})"

    query = f"""
        WITH EstoqueTotal AS (
            SELECT codpro, SUM(qtde) as total_estoque
            FROM estoque
            GROUP BY codpro
        )
        SELECT
            p.Tipo, p.Empresa, p.Num_Ped, p.Dt_Pedido, p.Dt_Entrega, p.Codcli, p.Nome_Cli,
            p.Codpro, p.Qt_Vend, p.Vlr_Liquido, p.Cod_Vend, p.Nome_Vend,
            prod.descricao as Descricao_Produto,
            prod.m2,
            COALESCE(et.total_estoque, 0) as estoque_total
        FROM pedidos p
        LEFT JOIN produtos prod ON p.Codpro = prod.codpro
        LEFT JOIN EstoqueTotal et ON p.Codpro = et.codpro
        WHERE {clausula_ano} AND {clausula_meses} {filtro_empresa} {filtro_vendedores} {filtro_tipo}
    """
    df = pd.read_sql_query(query, _conexao)

    if not df.empty:
        for col in ['Vlr_Liquido', 'Qt_Vend', 'm2', 'estoque_total']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        # Arredonda os rolos para o inteiro mais próximo
        df['Rolos'] = df.apply(lambda row: row['Qt_Vend'] / row['m2'] if pd.notna(row['m2']) and row['m2'] > 0 else 0, axis=1).round(0)
        df['Mes'] = pd.to_datetime(df['Dt_Entrega'], format='%d/%m/%Y', errors='coerce').dt.month.map(meses_pt)
        df['Tipo_Nome'] = df['Tipo'].map({'P': 'Pedido', 'C': 'Cotação'}).fillna(df['Tipo'])
        df['Empresa_Nome'] = df['Empresa'].astype(str).map({'1': 'CD', '3': 'Loja'}).fillna(df['Empresa'])
    return df

df_base = carregar_dados_pedidos(conn, ano_selecionado, meses_selecionados_nums, empresa_selecionada_id, vendedores_selecionados_ids, tipos_selecionados_ids)

# --- SEÇÃO PRINCIPAL ---
if 'pesquisa_pedidos' not in st.session_state:
    st.session_state.pesquisa_pedidos = ""

pesquisa = st.text_input(
    "Pesquisar por Cliente, Produto, Vendedor, Cód. Produto ou Nº Pedido (separe os termos por vírgula):",
    value=st.session_state.pesquisa_pedidos,
    key="pesquisa_pedidos_input"
)
st.session_state.pesquisa_pedidos = pesquisa

if st.button("Limpar Filtro da Pesquisa"):
    st.session_state.pesquisa_pedidos = ""
    st.rerun()

# --- FILTRAGEM DOS DADOS ---
df_filtrado = df_base.copy()
if not df_base.empty and st.session_state.pesquisa_pedidos:
    termos = [term.strip().lower() for term in st.session_state.pesquisa_pedidos.split(',') if term.strip()]
    colunas_pesquisa = ['Nome_Cli', 'Descricao_Produto', 'Nome_Vend', 'Codpro', 'Num_Ped']
    df_str_search = df_base[colunas_pesquisa].astype(str).apply(lambda x: x.str.lower())
    mascaras = [df_str_search.apply(lambda row: row.str.contains(term, na=False)).any(axis=1) for term in termos]
    mascara_final = np.logical_and.reduce(mascaras) if mascaras else pd.Series(True, index=df_base.index)
    df_filtrado = df_base[mascara_final]
st.markdown("---")

# --- VISUALIZAÇÃO DOS DADOS (TABELAS) ---
if not df_filtrado.empty:
    col1, col2 = st.columns(2)
    with col1:
        tipo_visualizacao = st.radio("Selecione o modo de visualização:", ["Detalhado por Cliente", "Agrupado por Mês"], horizontal=True)
    with col2:
        unidade_selecionada = st.radio("Visualizar valores em:", ["M²", "Rolos"], horizontal=True, key="unidade_global")
    st.markdown("---")

    formatter = lambda x: formatar_valor(x, decimais=0)

    if tipo_visualizacao == "Detalhado por Cliente":
        st.subheader("Visualização Detalhada por Cliente")
        
        total_valor_card = df_filtrado['Vlr_Liquido'].sum()
        if unidade_selecionada == "M²":
            label_qtd_card = f"Total Pedidos ({unidade_selecionada})"
            total_qtd_card = df_filtrado['Qt_Vend'].sum()
        else:
            label_qtd_card = f"Total Pedidos ({unidade_selecionada})"
            total_qtd_card = df_filtrado['Rolos'].sum()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            with st.container(border=True): st.metric(label="Total Pedidos", value=formatar_valor(df_filtrado['Num_Ped'].nunique()))
        with col2:
            with st.container(border=True): st.metric(label="Total Clientes", value=formatar_valor(df_filtrado['Codcli'].nunique()))
        with col3:
            with st.container(border=True): st.metric(label=label_qtd_card, value=formatar_valor(total_qtd_card, decimais=0))
        with col4:
            with st.container(border=True): st.metric(label="Total Valor", value=formatar_valor(total_valor_card, is_currency=True, decimais=0))
        st.markdown("---")

        df_display = df_filtrado.copy()
        
        colunas_base = ['Tipo_Nome', 'Empresa_Nome', 'Num_Ped', 'Nome_Vend', 'Dt_Pedido', 'Dt_Entrega', 'Nome_Cli', 'Codpro', 'Descricao_Produto', 'Vlr_Liquido']
        rename_map_base = {
            'Tipo_Nome': 'Tipo', 'Empresa_Nome': 'Empresa', 'Num_Ped': 'Nº Pedido', 'Nome_Vend': 'Vendedor', 'Dt_Pedido': 'Data Pedido',
            'Dt_Entrega': 'Data Entrega', 'Nome_Cli': 'Cliente', 'Codpro': 'Cód. Produto', 'Descricao_Produto': 'Descrição', 'Vlr_Liquido': 'Valor (R$)'
        }

        if unidade_selecionada == "M²":
            colunas_exibir = colunas_base + ['Qt_Vend', 'estoque_total']
            rename_map_final = {**rename_map_base, 'Qt_Vend': 'Qtde (m²)', 'estoque_total': 'Estoque (m²)'}
            colunas_numericas = ['Qtde (m²)', 'Estoque (m²)', 'Valor (R$)']
        else: # Rolos
            df_display['Estoque_Rolos'] = (df_display['estoque_total'] / df_display['m2']).fillna(0).round(0)
            colunas_exibir = colunas_base + ['Rolos', 'Estoque_Rolos']
            rename_map_final = {**rename_map_base, 'Rolos': 'Qtde (Rolos)', 'Estoque_Rolos': 'Estoque (Rolos)'}
            colunas_numericas = ['Qtde (Rolos)', 'Estoque (Rolos)', 'Valor (R$)']

        df_display = df_display[colunas_exibir].rename(columns=rename_map_final)
        
        st.dataframe(
            df_display.style.format(formatter, subset=colunas_numericas).set_properties(**{'text-align': 'right'}),
            width='stretch',
            hide_index=True
        )

    elif tipo_visualizacao == "Agrupado por Mês":
        st.subheader("Visualização Agrupada por Mês")
        
        total_valor_card = df_filtrado['Vlr_Liquido'].sum()
        df_produtos_unicos = df_filtrado[['Codpro', 'estoque_total', 'm2']].drop_duplicates()
        
        if unidade_selecionada == "M²":
            label_qtd_card = "Total Pedidos (m²)"
            total_qtd_card = df_filtrado['Qt_Vend'].sum()
            label_estoque_card = "Estoque Total (m²)"
            total_estoque_card = df_produtos_unicos['estoque_total'].sum()
        else: 
            label_qtd_card = "Total Pedidos (Rolos)"
            total_qtd_card = df_filtrado['Rolos'].sum()
            label_estoque_card = "Estoque Total (Rolos)"
            df_produtos_unicos['estoque_rolos'] = (df_produtos_unicos['estoque_total'] / df_produtos_unicos['m2']).fillna(0).round(0)
            total_estoque_card = df_produtos_unicos['estoque_rolos'].sum()
            
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            with st.container(border=True): st.metric(label="Total Pedidos", value=formatar_valor(df_filtrado['Num_Ped'].nunique()))
        with col2:
            with st.container(border=True): st.metric(label="Total Clientes", value=formatar_valor(df_filtrado['Codcli'].nunique()))
        with col3:
            with st.container(border=True): st.metric(label=label_qtd_card, value=formatar_valor(total_qtd_card, decimais=0))
        with col4:
            with st.container(border=True): st.metric(label=label_estoque_card, value=formatar_valor(total_estoque_card, decimais=0))
        with col5:
            with st.container(border=True): st.metric(label="Total Valor", value=formatar_valor(total_valor_card, is_currency=True, decimais=0))
        st.markdown("---")
        
        valor_agrupado = 'Qt_Vend' if unidade_selecionada == "M²" else 'Rolos'
        indice_pivot = ['Tipo_Nome', 'Empresa_Nome', 'Nome_Cli', 'Codpro', 'Descricao_Produto']
        ordem_meses = [meses_pt[i] for i in sorted(meses_selecionados_nums)]
        
        pivot_table = pd.pivot_table(df_filtrado, values=valor_agrupado, index=indice_pivot, columns='Mes', aggfunc='sum', fill_value=0).reindex(ordem_meses, axis=1, fill_value=0)
        pivot_table = pivot_table.reset_index()

        df_produto_info = df_filtrado[indice_pivot + ['estoque_total', 'm2']].drop_duplicates()
        
        df_final_agrupado = pd.merge(df_produto_info, pivot_table, on=indice_pivot, how='left')

        if unidade_selecionada == "Rolos":
            df_final_agrupado['estoque_final'] = (df_final_agrupado['estoque_total'] / df_final_agrupado['m2']).fillna(0).round(0)
            estoque_col_name = 'Estoque (Rolos)'
        else:
            df_final_agrupado['estoque_final'] = df_final_agrupado['estoque_total']
            estoque_col_name = 'Estoque (m²)'

        df_final_agrupado['Total'] = df_final_agrupado[ordem_meses].sum(axis=1)
        df_final_agrupado['Saldo'] = df_final_agrupado['Total'] - df_final_agrupado['estoque_final']
        df_final_agrupado = df_final_agrupado.sort_values(by='Total', ascending=False)
        
        colunas_finais = ['Tipo_Nome', 'Empresa_Nome', 'Nome_Cli', 'Codpro', 'Descricao_Produto'] + ordem_meses + ['estoque_final', 'Total', 'Saldo']
        df_final_agrupado = df_final_agrupado[colunas_finais].rename(columns={
            'Tipo_Nome': 'Tipo', 'Empresa_Nome': 'Empresa', 'Nome_Cli': 'Cliente', 'Codpro': 'Cód. Produto',
            'Descricao_Produto': 'Descrição', 'estoque_final': estoque_col_name
        })
        
        colunas_numericas = [estoque_col_name, 'Total', 'Saldo'] + ordem_meses
        
        st.dataframe(
            df_final_agrupado.style.format(formatter, subset=colunas_numericas).set_properties(**{'text-align': 'right'}),
            width='stretch',
            hide_index=True
        )
else:
    st.warning("Nenhum pedido encontrado para os filtros selecionados.")

conn.close()