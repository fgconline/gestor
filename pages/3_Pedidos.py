# pages/2_📋_Pedidos.py

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from io import BytesIO

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
# Checa se o usuário está logado
if not st.session_state.get("logged_in", False):
    st.error("Por favor, faça o login para acessar esta página.")
    st.stop()



# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(layout="wide")
st.title("📋 Análise de Pedidos")

# --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
if 'unidade_selecionada_pedidos' not in st.session_state:
    st.session_state.unidade_selecionada_pedidos = 'm2'

# --- FUNÇÕES ---
def criar_conexao():
    return sqlite3.connect('gestor.db')

def formatar_inteiro(valor):
    """Formata um número para o padrão #.### (sem casas decimais)"""
    try:
        return f"{valor:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return valor

@st.cache_data
def to_excel(df):
    output = BytesIO()
    df_export = df.copy()
    # Se o dataframe tiver um índice de múltiplas colunas (pivot), reseta o índice para exportação
    if isinstance(df_export.index, pd.MultiIndex):
        df_export.reset_index(inplace=True)
        
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Dados')
    processed_data = output.getvalue()
    return processed_data

@st.cache_data
def carregar_dados_pedidos():
    """Carrega os dados de pedidos usando um mapa de colunas definitivo."""
    try:
        conn = criar_conexao()
        query = "SELECT * FROM pedidos"
        df = pd.read_sql_query(query, conn)
        conn.close()

        mapa_definitivo = {
            'tipo': 'Tipo', 'numped': 'NumPed', 'dtpedido': 'Data',
            'dtentrega': 'Data_Entrega', 'codcli': 'Codcli', 'nomecli': 'Nome_do_Cliente',
            'codpro': 'Codpro', 'descricao': 'Descricao_do_Produto', 'qtvend': 'Qtde',
            'vlliquido': 'Valor_Total', 'nome_vendedor': 'Nome_do_Vendedor'
        }
        df.rename(columns=mapa_definitivo, inplace=True)

        vendedor_presente = 'Nome_do_Vendedor' in df.columns
        if vendedor_presente:
            df['Nome_do_Vendedor'] = df['Nome_do_Vendedor'].astype(str).fillna('Não Informado')
        
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        df['Data_Entrega'] = pd.to_datetime(df['Data_Entrega'], errors='coerce')
        df['Ano_Entrega'] = df['Data_Entrega'].dt.year
        df['Mes_Entrega'] = df['Data_Entrega'].dt.month

        conn = criar_conexao()
        df_produtos = pd.read_sql_query("SELECT CodPro, m2 FROM produtos", conn)
        conn.close()
        
        df['Codpro'] = df['Codpro'].astype(str)
        df_produtos['CodPro'] = df_produtos['CodPro'].astype(str)
        
        df = pd.merge(df, df_produtos, left_on='Codpro', right_on='CodPro', how='left')

        df['m2'] = df['m2'].fillna(1)
        df.loc[df['m2'] == 0, 'm2'] = 1
        df['Rolos'] = df['Qtde'] / df['m2']
        
        return df, vendedor_presente
    except Exception as e:
        st.error(f"Erro ao carregar dados de pedidos: {e}")
        return pd.DataFrame(), False

# --- LÓGICA PRINCIPAL ---
placeholder_cards = st.empty()
df_pedidos, vendedor_disponivel = carregar_dados_pedidos()

if df_pedidos.empty:
    st.warning("Nenhum dado de pedido encontrado.")
else:
    st.sidebar.header("Filtros")
    
    anos_disponiveis = sorted(df_pedidos['Ano_Entrega'].dropna().unique().astype(int))
    ano_atual = datetime.now().year
    default_ano = [ano_atual] if ano_atual in anos_disponiveis else anos_disponiveis
    anos_selecionados = st.sidebar.multiselect("Ano de Entrega:", options=anos_disponiveis, default=default_ano)

    nomes_meses_pt = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
    meses_disponiveis = sorted(df_pedidos['Mes_Entrega'].dropna().unique().astype(int))
    meses_selecionados_num = st.sidebar.multiselect("Mês de Entrega:", options=meses_disponiveis, format_func=lambda mes: nomes_meses_pt[mes], default=meses_disponiveis)

    tipos_disponiveis = sorted(df_pedidos['Tipo'].dropna().unique())
    tipos_selecionados = st.sidebar.multiselect("Tipo:", options=tipos_disponiveis, default=tipos_disponiveis)

    if vendedor_disponivel:
        df_temp_filtrado = df_pedidos[(df_pedidos['Ano_Entrega'].isin(anos_selecionados)) & (df_pedidos['Mes_Entrega'].isin(meses_selecionados_num)) & (df_pedidos['Tipo'].isin(tipos_selecionados))]
        vendedores_disponiveis = sorted(df_temp_filtrado['Nome_do_Vendedor'].unique())
        vendedores_selecionados = st.sidebar.multiselect("Vendedor(es):", options=vendedores_disponiveis, default=vendedores_disponiveis)

    df_filtrado = df_pedidos[(df_pedidos['Ano_Entrega'].isin(anos_selecionados)) & (df_pedidos['Mes_Entrega'].isin(meses_selecionados_num)) & (df_pedidos['Tipo'].isin(tipos_selecionados))]
    if vendedor_disponivel and vendedores_selecionados:
        df_filtrado = df_filtrado[df_filtrado['Nome_do_Vendedor'].isin(vendedores_selecionados)]

    st.write("---")
    
    col1_view, col2_view = st.columns(2)
    with col1_view:
        tipo_visualizacao = st.radio("Selecione o tipo de visualização:", ("Detalhado (Pedido a Pedido)", "Resumo Mensal"), horizontal=True)
    with col2_view:
        unidade = st.radio("Visualizar Quantidade em:", ('m2', 'Rolo'), key='unidade_selecionada_pedidos', horizontal=True)

    termo_pesquisa_input = st.text_input("Pesquisar por múltiplos itens (separados por vírgula)", placeholder="Ex: 9987, sulvisual, 1020")

    if termo_pesquisa_input:
        search_cols = ['NumPed', 'Nome_do_Cliente', 'Codpro', 'Descricao_do_Produto']
        if vendedor_disponivel: search_cols.append('Nome_do_Vendedor')
        for col in search_cols:
            if col in df_filtrado.columns: df_filtrado[col] = df_filtrado[col].astype(str)
        termos_pesquisa = [termo.strip().lower() for termo in termo_pesquisa_input.split(',') if termo.strip()]
        mascara_final = pd.Series(True, index=df_filtrado.index)
        for termo in termos_pesquisa:
            mascara_termo = df_filtrado[search_cols].apply(lambda row: ' '.join(row.values).lower(), axis=1).str.contains(termo, na=False)
            mascara_final &= mascara_termo
        df_filtrado = df_filtrado[mascara_final]
    
    if df_filtrado.empty:
        st.info("Nenhum pedido encontrado para os filtros e pesquisa selecionados.")
        placeholder_cards.empty()
    else:
        with placeholder_cards.container():
            total_pedidos = df_filtrado['NumPed'].nunique()
            clientes_distintos = df_filtrado['Nome_do_Cliente'].nunique()
            produtos_distintos = df_filtrado['Codpro'].nunique()
            valor_total_filtrado = df_filtrado['Valor_Total'].sum()
            label_quantidade = f"Quantidade ({st.session_state.unidade_selecionada_pedidos})"
            quantidade_total = df_filtrado['Qtde'].sum() if st.session_state.unidade_selecionada_pedidos == 'm2' else df_filtrado['Rolos'].sum()
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                with st.container(border=True): st.metric(label="Total de Pedidos", value=formatar_inteiro(total_pedidos))
            with col2:
                with st.container(border=True): st.metric(label="Clientes Distintos", value=formatar_inteiro(clientes_distintos))
            with col3:
                with st.container(border=True): st.metric(label="Produtos Distintos", value=formatar_inteiro(produtos_distintos))
            with col4:
                with st.container(border=True): st.metric(label=label_quantidade, value=formatar_inteiro(quantidade_total))
            with col5:
                with st.container(border=True): st.metric(label="Valor Total", value=f"R$ {formatar_inteiro(valor_total_filtrado)}")

        st.write("---")
        
        if tipo_visualizacao == "Detalhado (Pedido a Pedido)":
            df_display = df_filtrado.copy()
            if st.session_state.unidade_selecionada_pedidos == 'm2':
                df_display.rename(columns={'Qtde': 'Quantidade'}, inplace=True)
            else:
                df_display.rename(columns={'Rolos': 'Quantidade'}, inplace=True)
            
            df_para_exibir = df_display.rename(columns={'NumPed': 'Número do Pedido', 'Data_Entrega': 'Data Entrega', 'Nome_do_Cliente': 'Cliente', 'Nome_do_Vendedor': 'Vendedor', 'Codpro': 'Cód. Produto', 'Descricao_do_Produto': 'Descrição', 'Valor_Total': 'Valor Total'})
            
            colunas_finais = ['Tipo', 'Número do Pedido', 'Data', 'Data Entrega', 'Cliente', 'Vendedor', 'Cód. Produto', 'Descrição', 'Quantidade', 'Valor Total']
            if not vendedor_disponivel: colunas_finais.remove('Vendedor')
            
            col_titulo, col_botao = st.columns([0.75, 0.25])
            with col_titulo:
                st.subheader("Detalhes dos Pedidos")
            with col_botao:
                excel_data = to_excel(df_para_exibir[colunas_finais])
                st.download_button(label="📥 Exportar para Excel", data=excel_data, file_name=f'pedidos_detalhados_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            st.dataframe(df_para_exibir, use_container_width=True, hide_index=True, column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"), "Data Entrega": st.column_config.DateColumn("Data Entrega", format="DD/MM/YYYY"), "Quantidade": st.column_config.NumberColumn(format="%.0f"), "Valor Total": st.column_config.NumberColumn(format="R$ %.2f")}, column_order=colunas_finais)
        
        else: # Resumo Mensal
            df_pivot = df_filtrado.copy()
            
            titulo_unidade = st.session_state.unidade_selecionada_pedidos
            if titulo_unidade == 'm2':
                df_pivot['Quantidade'] = df_pivot['Qtde']
            else:
                df_pivot['Quantidade'] = df_pivot['Rolos']
            
            df_pivot['Data_Entrega_Formatada'] = df_pivot['Data_Entrega'].dt.strftime('%d/%m/%Y')
            
            index_cols = ['Tipo', 'NumPed', 'Data_Entrega_Formatada', 'Nome_do_Cliente']
            index_names = ['Tipo', 'Nº Pedido', 'Dt. Entrega', 'Cliente']
            if vendedor_disponivel:
                index_cols.append('Nome_do_Vendedor')
                index_names.append('Vendedor')
            index_cols.extend(['Codpro', 'Descricao_do_Produto'])
            index_names.extend(['Cód. Produto', 'Descrição'])

            tabela_pivot = pd.pivot_table(df_pivot, index=index_cols, columns='Mes_Entrega', values='Quantidade', aggfunc='sum', fill_value=0)

            tabela_pivot.index.names = index_names
            tabela_pivot.rename(columns={k: v for k, v in nomes_meses_pt.items() if k in tabela_pivot.columns}, inplace=True)

            col_titulo, col_botao = st.columns([0.75, 0.25])
            with col_titulo:
                st.subheader(f"Resumo Mensal de Quantidade ({titulo_unidade})")
            with col_botao:
                excel_data = to_excel(tabela_pivot)
                st.download_button(label="📥 Exportar para Excel", data=excel_data, file_name=f'resumo_mensal_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            st.dataframe(tabela_pivot.style.format(formatar_inteiro), use_container_width=True)