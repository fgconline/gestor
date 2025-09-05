# pages/6_⚖️_Reservas.py

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime


# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
# Checa se o usuário está logado
if not st.session_state.get("logged_in", False):
    st.error("Por favor, faça o login para acessar esta página.")
    st.stop()


# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(layout="wide")
st.title("⚖️ Reservas e Atendimento de Pedidos")

# --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
if 'unidade_reservas' not in st.session_state:
    st.session_state.unidade_reservas = 'm2'

# --- FUNÇÕES ---
def criar_conexao():
    return sqlite3.connect('gestor.db')

@st.cache_data
def carregar_dados_base():
    """Carrega todas as tabelas necessárias do banco de dados e padroniza as chaves."""
    try:
        conn = criar_conexao()
        df_pedidos = pd.read_sql_query("SELECT * FROM pedidos", conn)
        df_imports = pd.read_sql_query("SELECT * FROM importacoes", conn)
        df_estoque = pd.read_sql_query("SELECT * FROM estoque", conn)
        df_produtos = pd.read_sql_query("SELECT * FROM produtos", conn)
        conn.close()
        
        df_produtos['CodPro'] = df_produtos['CodPro'].astype(str)
        df_estoque['CodPro'] = df_estoque['CodPro'].astype(str)
        df_imports['CodPro'] = df_imports['CodPro'].astype(str)
        df_pedidos['codpro'] = df_pedidos['codpro'].astype(str)
        
        return df_pedidos, df_imports, df_estoque, df_produtos
    except Exception as e:
        st.error(f"Erro ao carregar dados base: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def calcular_reservas(df_pedidos, df_imports, df_estoque, df_produtos, ano, meses, vendedores):
    """
    Executa a simulação de reservas com base nos dados e filtros.
    """
    mapa_pedidos = {
        'tipo': 'Tipo', 'numped': 'NumPed', 'dtpedido': 'Data', 'dtentrega': 'Data_Entrega',
        'codcli': 'Codcli', 'nomecli': 'Nome_do_Cliente', 'codpro': 'CodPro',
        'descricao': 'Descricao_do_Produto', 'qtvend': 'Qtde', 'nome_vendedor': 'Nome_do_Vendedor'
    }
    df_pedidos.rename(columns=mapa_pedidos, inplace=True)
    df_pedidos['Data_Entrega'] = pd.to_datetime(df_pedidos['Data_Entrega'], errors='coerce')
    df_pedidos = df_pedidos.dropna(subset=['Data_Entrega'])
    df_pedidos_filtrado = df_pedidos[
        (df_pedidos['Data_Entrega'].dt.year == ano) &
        (df_pedidos['Data_Entrega'].dt.month.isin(meses)) &
        (df_pedidos['Nome_do_Vendedor'].isin(vendedores))
    ].sort_values(by='Data_Entrega')

    if df_pedidos_filtrado.empty:
        return pd.DataFrame()

    df_imports['Previsao_Chegada'] = pd.to_datetime(df_imports['Previsao_Chegada'], errors='coerce')
    for col in ['Status_Fabrica', 'Recebido', 'Reservado']:
        df_imports[col] = df_imports[col].fillna('').astype(str)
    df_imports_filtrado = df_imports[
        (df_imports['Previsao_Chegada'].dt.year == ano) &
        (df_imports['Previsao_Chegada'].dt.month.isin(meses)) &
        (df_imports['Status_Fabrica'].str.lower() != 'nao atendida') &
        (df_imports['Recebido'].str.lower().isin(['nao', 'não'])) &
        (df_imports['Reservado'].str.lower().isin(['nao', 'não']))
    ]
    importacoes_por_produto = df_imports_filtrado.groupby('CodPro')['M2'].sum()

    df_estoque['Estoque'] = df_estoque['Estoque_1'] + df_estoque['Estoque_3'] + df_estoque['Estoque_19']
    estoque_por_produto = df_estoque.set_index('CodPro')['Estoque']

    resultados = []
    produtos_processados = df_pedidos_filtrado['CodPro'].unique()

    for codpro in produtos_processados:
        estoque_inicial = estoque_por_produto.get(codpro, 0)
        importacoes_periodo = importacoes_por_produto.get(codpro, 0)
        disponibilidade_atual = estoque_inicial + importacoes_periodo
        
        pedidos_produto = df_pedidos_filtrado[df_pedidos_filtrado['CodPro'] == codpro]

        for _, pedido in pedidos_produto.iterrows():
            disponibilidade_antes_do_pedido = disponibilidade_atual
            qtd_pedida = pedido['Qtde']
            atendido = 0
            
            if disponibilidade_atual >= qtd_pedida:
                atendido = qtd_pedida; status = "Atendido Total"
            elif disponibilidade_atual > 0:
                atendido = disponibilidade_atual; status = "Atendido Parcial"
            else:
                status = "Pendente"
            
            disponibilidade_atual -= atendido

            resultados.append({
                'Cliente': pedido['Nome_do_Cliente'], 'Pedido': pedido['NumPed'], 'Data_Entrega': pedido['Data_Entrega'],
                'Vendedor': pedido['Nome_do_Vendedor'], 'CodPro': codpro,
                'Descricao': pedido['Descricao_do_Produto'], 'Disponivel': disponibilidade_antes_do_pedido,
                'Qtd. Pedido': qtd_pedida, 'Status': status, 'Atende': atendido,
                'Pendente': qtd_pedida - atendido, 'Saldo': disponibilidade_atual
            })

    if not resultados:
        return pd.DataFrame()

    df_resultado = pd.DataFrame(resultados)
    df_resultado = pd.merge(df_resultado, df_produtos[['CodPro', 'm2']], on='CodPro', how='left')
    df_resultado['m2'] = df_resultado['m2'].fillna(1).replace(0, 1)
    return df_resultado

# --- LÓGICA PRINCIPAL ---
placeholder_cards = st.empty()
df_pedidos, df_imports, df_estoque, df_produtos = carregar_dados_base()

if df_pedidos.empty or df_imports.empty or df_estoque.empty:
    st.warning("Uma ou mais tabelas (pedidos, importacoes, estoque) não foram encontradas.")
else:
    st.sidebar.header("Filtros")
    ano_atual = datetime.now().year
    ano_selecionado = st.sidebar.selectbox("Ano de Entrega", options=range(ano_atual - 2, ano_atual + 3), index=2)

    nomes_meses_pt = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
    meses_selecionados = st.sidebar.multiselect(
        "Mês(es) de Entrega", options=list(nomes_meses_pt.keys()),
        format_func=lambda mes: nomes_meses_pt[mes], default=list(nomes_meses_pt.keys())
    )

    vendedores_disponiveis = sorted(df_pedidos['nome_vendedor'].dropna().unique())
    vendedores_selecionados = st.sidebar.multiselect("Vendedor(es)", options=vendedores_disponiveis, default=vendedores_disponiveis)
    
    df_reservas = calcular_reservas(df_pedidos, df_imports, df_estoque, df_produtos, ano_selecionado, meses_selecionados, vendedores_selecionados)

    st.write("---")
    unidade = st.radio("Visualizar em:", ('m2', 'Rolo'), key='unidade_reservas', horizontal=True)

    termo_pesquisa_input = st.text_input("Pesquisar por múltiplos itens", placeholder="Ex: 9987, sulvisual, 1020")

    df_filtrado = df_reservas.copy()
    if not df_filtrado.empty and termo_pesquisa_input:
        df_filtrado[['CodPro', 'Descricao', 'Cliente', 'Pedido', 'Vendedor']] = df_filtrado[['CodPro', 'Descricao', 'Cliente', 'Pedido', 'Vendedor']].astype(str)
        termos_pesquisa = [termo.strip().lower() for termo in termo_pesquisa_input.split(',') if termo.strip()]
        
        mascara_final = pd.Series(True, index=df_filtrado.index)
        search_cols = ['Cliente', 'Pedido', 'CodPro', 'Descricao', 'Vendedor']
        df_para_pesquisa = df_filtrado[search_cols]

        for termo in termos_pesquisa:
            mascara_termo = df_para_pesquisa.apply(lambda row: any(termo in str(cell).lower() for cell in row), axis=1)
            mascara_final &= mascara_termo
        
        df_filtrado = df_filtrado[mascara_final]

    if df_filtrado.empty:
        st.info("Nenhum resultado para os filtros e pesquisa selecionados.")
        placeholder_cards.empty()
    else:
        # --- CÁLCULO E EXIBIÇÃO DOS CARDS (LÓGICA CORRIGIDA) ---
        with placeholder_cards.container():
            df_cards = df_filtrado.copy()
            label_unidade = f"({st.session_state.unidade_reservas})"
            
            # Totais base em m2
            df_disponibilidade = df_cards.drop_duplicates(subset=['CodPro'], keep='first')
            total_disponibilidade_m2 = df_disponibilidade['Disponivel'].sum()
            total_pedidos_m2 = df_cards['Qtd. Pedido'].sum()
            total_pendente_m2 = df_cards['Pendente'].sum()
            
            produtos_na_tabela = df_cards['CodPro'].unique()
            df_estoque_filtrado = df_estoque[df_estoque['CodPro'].isin(produtos_na_tabela)]
            total_estoque_m2 = df_estoque_filtrado['Estoque'].sum()
            
            total_importacao_m2 = total_disponibilidade_m2 - total_estoque_m2
            total_atendido_m2 = total_pedidos_m2 - total_pendente_m2
            saldo_final_m2 = total_disponibilidade_m2 - total_atendido_m2

            # Converte para Rolos se necessário
            if st.session_state.unidade_reservas == 'Rolo':
                # O df_cards já tem a coluna 'm2', a conversão é direta
                total_disponibilidade = (df_disponibilidade['Disponivel'] / df_disponibilidade['m2']).sum()
                total_pedidos = (df_cards['Qtd. Pedido'] / df_cards['m2']).sum()
                total_pendente = (df_cards['Pendente'] / df_cards['m2']).sum()

                # Apenas o estoque precisa de merge para obter o 'm2'
                df_estoque_conv = pd.merge(df_estoque_filtrado, df_produtos[['CodPro', 'm2']], on='CodPro', how='left')
                df_estoque_conv['m2'] = df_estoque_conv['m2'].fillna(1).replace(0,1)
                total_estoque = (df_estoque_conv['Estoque'] / df_estoque_conv['m2']).sum()
                
                total_importacao = total_disponibilidade - total_estoque
                saldo_final = total_disponibilidade - (total_pedidos - total_pendente)
            else:
                total_disponibilidade, total_importacao, total_pedidos, total_pendente, saldo_final, total_estoque = \
                total_disponibilidade_m2, total_importacao_m2, total_pedidos_m2, total_pendente_m2, saldo_final_m2, total_estoque_m2

            # Exibe os 5 Cards Corretos
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                with st.container(border=True): st.metric(label=f"Estoque Total {label_unidade}", value=f"{total_estoque:,.0f}".replace(",","."))
            with col2:
                with st.container(border=True): st.metric(label=f"Total Import. {label_unidade}", value=f"{total_importacao:,.0f}".replace(",","."))
            with col3:
                with st.container(border=True): st.metric(label=f"Total Pedidos {label_unidade}", value=f"{total_pedidos:,.0f}".replace(",","."))
            with col4:
                with st.container(border=True): st.metric(label=f"Pendente {label_unidade}", value=f"{total_pendente:,.0f}".replace(",","."))
            with col5:
                with st.container(border=True): st.metric(label=f"Saldo Final {label_unidade}", value=f"{saldo_final:,.0f}".replace(",","."))

        # --- PREPARAÇÃO E EXIBIÇÃO DA TABELA FINAL ---
        df_display = df_filtrado.copy()
        if st.session_state.unidade_reservas == 'Rolo':
            for col in ['Disponivel', 'Qtd. Pedido', 'Atende', 'Pendente', 'Saldo']:
                if col in df_display.columns:
                    df_display[col] = df_display[col] / df_display['m2']

        colunas_para_exibir = ['Cliente', 'Pedido', 'Data_Entrega', 'Vendedor', 'CodPro', 'Descricao', 'Disponivel', 'Qtd. Pedido', 'Status', 'Atende', 'Pendente', 'Saldo']
        df_para_exibir = df_display[colunas_para_exibir].rename(columns={'CodPro': 'Cód. Produto', 'Descricao': 'Descrição', 'Data_Entrega': 'Data Entrega'})

        st.dataframe(
            df_para_exibir,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Pedido": st.column_config.NumberColumn(),
                "Data Entrega": st.column_config.DateColumn("Data Entrega", format="DD/MM/YYYY"),
                "Disponivel": st.column_config.NumberColumn("Disponível", format="%.0f"),
                "Qtd. Pedido": st.column_config.NumberColumn(format="%.0f"),
                "Atende": st.column_config.NumberColumn(format="%.0f"),
                "Pendente": st.column_config.NumberColumn(format="%.0f"),
                "Saldo": st.column_config.NumberColumn(format="%.0f"),
            }
        )