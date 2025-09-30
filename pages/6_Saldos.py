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
st.set_page_config(page_title="Saldos", page_icon="⚖️", layout="wide")
st.title("⚖️ Análise de Saldos (Estoque x Pedidos x Importações)")

if st.button("🔄 Atualizar Dados"):
    st.cache_data.clear()
    st.toast("Dados atualizados!", icon="✅")
    st.rerun()
st.markdown("---")

# --- FUNÇÕES E CARREGAMENTO DE DADOS ---
DB_FILE = "gestor_mkt.db"

def formatar_valor(valor):
    if pd.isna(valor) or not isinstance(valor, (int, float, complex)): return ""
    return f"{valor:,.0f}".replace(",", ".")

@st.cache_data(ttl=600)
def carregar_dados_base():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        df_produtos = pd.read_sql_query("SELECT codpro, descricao, m2 FROM produtos", conn)
        df_estoque = pd.read_sql_query("SELECT codpro, qtde, deposito FROM estoque", conn)
        df_imports = pd.read_sql_query("SELECT CodPro as codpro, Data_prevista, M2, Rolos, Status_fabrica, Recebido, reservado FROM imports", conn)
        df_pedidos = pd.read_sql_query("SELECT Codpro as codpro, Dt_Entrega, Qt_Vend, Tipo, Num_Ped, Nome_Vend, Nome_Cli FROM pedidos", conn)
        conn.close()

        df_pedidos = df_pedidos.merge(df_produtos[['codpro', 'm2']], on='codpro', how='left')
        df_pedidos['m2'] = pd.to_numeric(df_pedidos['m2'], errors='coerce')
        df_pedidos['Qt_Vend'] = pd.to_numeric(df_pedidos['Qt_Vend'], errors='coerce')
        df_pedidos['Rolos'] = (df_pedidos['Qt_Vend'] / df_pedidos['m2']).fillna(0).round(0)

        for df, date_col in [(df_imports, 'Data_prevista'), (df_pedidos, 'Dt_Entrega')]:
            df[date_col] = pd.to_datetime(df[date_col], format='%d/%m/%Y', errors='coerce')
        
        return df_produtos, df_estoque, df_imports, df_pedidos
    except Exception as e:
        st.error(f"Erro ao carregar dados base: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_produtos_base, df_estoque_base, df_imports_base, df_pedidos_base = carregar_dados_base()

# --- INÍCIO DA PÁGINA ---
if df_produtos_base.empty:
    st.warning("Tabela de produtos não encontrada. Por favor, realize o upload do arquivo 'produtos.csv'.")
else:
    st.sidebar.header("Filtros")
    anos_disponiveis = sorted(pd.concat([df_imports_base['Data_prevista'].dt.year, df_pedidos_base['Dt_Entrega'].dt.year]).dropna().unique(), reverse=True)
    anos_disponiveis_int = [int(a) for a in anos_disponiveis]
    
    agora = datetime.now()
    ano_atual = agora.year
    mes_atual_num = agora.month
    
    # Define o índice padrão para o ano atual
    try:
        index_ano_atual = anos_disponiveis_int.index(ano_atual)
    except ValueError:
        index_ano_atual = 0
    
    ano_selecionado = st.sidebar.selectbox("Ano", anos_disponiveis_int, index=index_ano_atual)

    meses_pt = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
    
    # Define os meses padrão: do mês atual em diante
    if ano_selecionado == ano_atual:
        meses_default_nomes = [v for k, v in meses_pt.items() if k >= mes_atual_num]
    else:
        meses_default_nomes = list(meses_pt.values()) # Se não for o ano atual, seleciona todos

    meses_selecionados_nomes = st.sidebar.multiselect("Mês(es)", list(meses_pt.values()), default=meses_default_nomes)
    meses_selecionados_nums = [k for k, v in meses_pt.items() if v in meses_selecionados_nomes]
    
    unidade = st.radio("Visualizar por:", ["M²", "Rolos"], horizontal=True, key="saldos_unidade")

    df_pedidos_filtrado = df_pedidos_base[(df_pedidos_base['Dt_Entrega'].dt.year == ano_selecionado) & (df_pedidos_base['Dt_Entrega'].dt.month.isin(meses_selecionados_nums))] if not df_pedidos_base.empty else pd.DataFrame()
    df_imports_filtrado = df_imports_base[(df_imports_base['Data_prevista'].dt.year == ano_selecionado) & (df_imports_base['Data_prevista'].dt.month.isin(meses_selecionados_nums)) & (df_imports_base['Status_fabrica'] != 'NÃO ATENDIDO') & (df_imports_base['Recebido'] == 'não') & (df_imports_base['reservado'] == 'não')] if not df_imports_base.empty else pd.DataFrame()

    tabela1 = df_produtos_base[['codpro', 'descricao']].copy().rename(columns={'descricao': 'Produto'})
    col_estoque = 'qtde' if unidade == 'M²' else 'qtde_rolos'
    if not df_estoque_base.empty:
        df_estoque_base['m2'] = pd.to_numeric(df_estoque_base.merge(df_produtos_base, on='codpro', how='left')['m2'], errors='coerce')
        df_estoque_base['qtde'] = pd.to_numeric(df_estoque_base['qtde'], errors='coerce').fillna(0)
        df_estoque_base['qtde_rolos'] = (df_estoque_base['qtde'] / df_estoque_base['m2']).fillna(0).round(0)
        df_estoque_pivot = df_estoque_base.pivot_table(index='codpro', columns='deposito', values=col_estoque, aggfunc='sum')
        tabela1 = tabela1.merge(df_estoque_pivot, on='codpro', how='left')

    col_imports = 'M2' if unidade == 'M²' else 'Rolos'
    col_pedidos = 'Qt_Vend' if unidade == 'M²' else 'Rolos'
    df_imports_agg = df_imports_filtrado.groupby('codpro', as_index=False)[col_imports].sum().rename(columns={col_imports: 'Importação'})
    df_pedidos_agg = df_pedidos_filtrado.groupby('codpro', as_index=False)[col_pedidos].sum().rename(columns={col_pedidos: 'Pedidos'})
    
    tabela1 = tabela1.merge(df_imports_agg, on='codpro', how='left')
    tabela1 = tabela1.merge(df_pedidos_agg, on='codpro', how='left')
    
    hubs = [col for col in ['hub1', 'hub3', 'hub19'] if col in tabela1.columns]
    for hub in ['hub1', 'hub3', 'hub19']:
        if hub not in tabela1.columns: tabela1[hub] = 0
    tabela1[hubs + ['Importação', 'Pedidos']] = tabela1[hubs + ['Importação', 'Pedidos']].fillna(0)
    
    tabela1['Total Estoque'] = tabela1[hubs].sum(axis=1)
    tabela1['Saldo'] = tabela1['Total Estoque'] + tabela1['Importação'] - tabela1['Pedidos']

    pesquisa1 = st.text_input("Pesquisar na tabela de saldos (separe termos por vírgula):")
    tabela1_filtrada = tabela1.copy()
    if pesquisa1:
        termos = [term.strip().lower() for term in pesquisa1.split(',') if term.strip()]
        for termo in termos:
            tabela1_filtrada = tabela1_filtrada[tabela1_filtrada.astype(str).apply(lambda row: row.str.lower().str.contains(termo, na=False)).any(axis=1)]

    st.markdown("---")
    st.subheader("Resumo dos Saldos")
    total_produtos = len(tabela1_filtrada)
    total_estoque = tabela1_filtrada['Total Estoque'].sum()
    total_importacao = tabela1_filtrada['Importação'].sum()
    total_pedidos = tabela1_filtrada['Pedidos'].sum()
    total_saldo = tabela1_filtrada['Saldo'].sum()
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1, st.container(border=True): st.metric("Total de Produtos", formatar_valor(total_produtos))
    with c2, st.container(border=True): st.metric(f"Total Estoque ({unidade})", formatar_valor(total_estoque))
    with c3, st.container(border=True): st.metric(f"Total Importação ({unidade})", formatar_valor(total_importacao))
    with c4, st.container(border=True): st.metric(f"Total Pedidos ({unidade})", formatar_valor(total_pedidos))
    with c5, st.container(border=True): st.metric(f"Saldo ({unidade})", formatar_valor(total_saldo))
    st.markdown("---")

    st.subheader("Tabela de Saldos Detalhada")
    colunas_tabela1 = ['codpro', 'Produto'] + hubs + ['Total Estoque', 'Importação', 'Pedidos', 'Saldo']
    colunas_numericas1 = hubs + ['Total Estoque', 'Importação', 'Pedidos', 'Saldo']
    st.dataframe(tabela1_filtrada[colunas_tabela1].style.format(formatar_valor, subset=colunas_numericas1).set_properties(**{'text-align': 'right'}, subset=colunas_numericas1), width='stretch', hide_index=True)

    st.markdown("---")
    st.subheader("Detalhes de Pedidos no Período")
    pesquisa2 = st.text_input("Pesquisar nos detalhes de pedidos (separe termos por vírgula):", key="pesquisa_pedidos")
    
    df_pedidos_detalhe = df_pedidos_filtrado.merge(df_produtos_base[['codpro', 'descricao']], on='codpro', how='left')
    
    if pesquisa2:
        termos = [term.strip().lower() for term in pesquisa2.split(',') if term.strip()]
        for termo in termos:
            df_pedidos_detalhe = df_pedidos_detalhe[df_pedidos_detalhe.astype(str).apply(lambda row: row.str.lower().str.contains(termo, na=False)).any(axis=1)]

    if not df_pedidos_detalhe.empty:
        df_pedidos_detalhe['Mes'] = df_pedidos_detalhe['Dt_Entrega'].dt.month
        
        tabela2_pivot = df_pedidos_detalhe.pivot_table(
            index=['Tipo', 'Num_Ped', 'Nome_Cli', 'Nome_Vend', 'codpro', 'descricao'], 
            columns='Mes', 
            values=col_pedidos, 
            aggfunc='sum'
        ).fillna(0)
        
        tabela2_pivot = tabela2_pivot.rename(columns=meses_pt)
        tabela2_pivot['Total'] = tabela2_pivot.sum(axis=1)
        
        tabela2_final = tabela2_pivot.reset_index().rename(columns={
            'descricao': 'Produto', 'Num_Ped': 'Pedido', 'Nome_Cli': 'Cliente', 'Nome_Vend': 'Vendedor'
        })
        
        meses_na_tabela = [meses_pt[m] for m in sorted(df_pedidos_detalhe['Mes'].unique()) if m in meses_pt]
        colunas_numericas2 = meses_na_tabela + ['Total']

        total_row = tabela2_final[colunas_numericas2].sum().to_dict()
        total_row['Produto'] = 'TOTAL'
        tabela2_final = pd.concat([tabela2_final, pd.DataFrame([total_row])], ignore_index=True)

        ordem_cols_2 = ['Tipo', 'Pedido', 'Cliente', 'Vendedor', 'codpro', 'Produto'] + meses_na_tabela + ['Total']
        
        st.dataframe(
            tabela2_final[ordem_cols_2].style.format(formatar_valor, subset=colunas_numericas2)
                                        .set_properties(**{'text-align': 'right'}, subset=colunas_numericas2), 
            width='stretch', 
            hide_index=True
        )
    else:
        st.write("Nenhum detalhe de pedido encontrado para os filtros selecionados.")