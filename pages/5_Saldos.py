# pages/5_🔢_Saldos.py

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
if not st.session_state.get("logged_in", False):
    st.error("Por favor, faça o login para acessar esta página.")
    st.stop()

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(layout="wide")
st.title("🔢 Saldos de Estoque")

# --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
if 'unidade_saldos' not in st.session_state:
    st.session_state.unidade_saldos = 'm2'

# --- FUNÇÕES ---
def criar_conexao():
    """Cria e retorna uma conexão com o banco de dados SQLite."""
    return sqlite3.connect('gestor.db')

def formatar_inteiro(valor):
    """Formata um número para o padrão #.### (sem casas decimais)"""
    try:
        # Arredonda antes de formatar para garantir que não haja casas decimais
        valor_arredondado = round(valor or 0)
        return f"{valor_arredondado:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return valor

@st.cache_data
def carregar_dados_saldos(ano_selecionado, meses_selecionados):
    """
    Carrega e consolida dados de estoque (por hub + total), importações e pedidos
    com base no schema real do DB.
    """
    try:
        conn = criar_conexao()

        # 1) Lista mestre de produtos
        df_produtos = pd.read_sql_query(
            "SELECT CodPro, Descricao, m2 FROM produtos", conn
        )
        df_produtos['CodPro'] = df_produtos['CodPro'].astype(str)

        # 2) ESTOQUE por hub + total
        df_estoque_raw = pd.read_sql_query(
            "SELECT CodPro, Estoque_1, Estoque_3, Estoque_19 FROM estoque", conn
        )
        df_estoque_raw['CodPro'] = df_estoque_raw['CodPro'].astype(str)

        for c in ['Estoque_1', 'Estoque_3', 'Estoque_19']:
            if c in df_estoque_raw.columns:
                df_estoque_raw[c] = pd.to_numeric(df_estoque_raw[c], errors='coerce').fillna(0)
            else:
                df_estoque_raw[c] = 0

        df_estoque_raw['Estoque_Total'] = (
            df_estoque_raw['Estoque_1'] + df_estoque_raw['Estoque_3'] + df_estoque_raw['Estoque_19']
        )
        df_estoque = df_estoque_raw[['CodPro', 'Estoque_1', 'Estoque_3', 'Estoque_19', 'Estoque_Total']]

        # 3) IMPORTAÇÕES (pendentes, por período)
        query_imports = """
            SELECT CodPro, M2 as Qtde, Previsao_Chegada
            FROM importacoes
            WHERE LOWER(Recebido) IN ('nao', 'não')
              AND LOWER(Reservado) IN ('nao', 'não')
        """
        df_imports = pd.read_sql_query(query_imports, conn)
        df_imports_agg = pd.DataFrame(columns=['CodPro', 'Importacoes']) # Inicializa vazio
        if not df_imports.empty:
            df_imports['Previsao_Chegada'] = pd.to_datetime(df_imports['Previsao_Chegada'], errors='coerce')
            df_imports['Ano'] = df_imports['Previsao_Chegada'].dt.year
            df_imports['Mes'] = df_imports['Previsao_Chegada'].dt.month
            df_imports_filtrado = df_imports[
                (df_imports['Ano'] == ano_selecionado) &
                (df_imports['Mes'].isin(meses_selecionados))
            ]
            if not df_imports_filtrado.empty:
                df_imports_agg = (
                    df_imports_filtrado.groupby('CodPro')['Qtde']
                    .sum().reset_index().rename(columns={'Qtde': 'Importacoes'})
                )
                df_imports_agg['CodPro'] = df_imports_agg['CodPro'].astype(str)

        # 4) PEDIDOS (por período)
        df_pedidos = pd.read_sql_query("SELECT codpro, qtvend, dtentrega FROM pedidos", conn)
        df_pedidos_agg = pd.DataFrame(columns=['CodPro', 'Pedidos']) # Inicializa vazio
        if not df_pedidos.empty:
            df_pedidos.rename(
                columns={'codpro': 'CodPro', 'qtvend': 'Qtde', 'dtentrega': 'Data_Entrega'},
                inplace=True
            )
            df_pedidos['Data_Entrega'] = pd.to_datetime(df_pedidos['Data_Entrega'], errors='coerce')
            df_pedidos['Ano'] = df_pedidos['Data_Entrega'].dt.year
            df_pedidos['Mes'] = df_pedidos['Data_Entrega'].dt.month
            df_pedidos_filtrado = df_pedidos[
                (df_pedidos['Ano'] == ano_selecionado) &
                (df_pedidos['Mes'].isin(meses_selecionados))
            ]
            if not df_pedidos_filtrado.empty:
                df_pedidos_agg = (
                    df_pedidos_filtrado.groupby('CodPro')['Qtde']
                    .sum().reset_index().rename(columns={'Qtde': 'Pedidos'})
                )
                df_pedidos_agg['CodPro'] = df_pedidos_agg['CodPro'].astype(str)

        # 5) Junta tudo
        df_final = pd.merge(df_produtos, df_estoque, on='CodPro', how='left')
        df_final = pd.merge(df_final, df_imports_agg, on='CodPro', how='left')
        df_final = pd.merge(df_final, df_pedidos_agg, on='CodPro', how='left')

        for c in ['Estoque_1', 'Estoque_3', 'Estoque_19', 'Estoque_Total', 'Importacoes', 'Pedidos']:
            if c not in df_final.columns:
                df_final[c] = 0
            df_final[c] = pd.to_numeric(df_final[c], errors='coerce').fillna(0)

        df_final['Saldo'] = (df_final['Estoque_Total'] + df_final['Importacoes']) - df_final['Pedidos']

        # 6) Conversão para "Rolo" (usa m2 do produto; evita zero/divisão)
        df_final['m2'] = pd.to_numeric(df_final['m2'], errors='coerce').fillna(1)
        df_final.loc[df_final['m2'] == 0, 'm2'] = 1

        df_final['Estoque_1_Rolo']    = df_final['Estoque_1']    / df_final['m2']
        df_final['Estoque_3_Rolo']    = df_final['Estoque_3']    / df_final['m2']
        df_final['Estoque_19_Rolo']   = df_final['Estoque_19']   / df_final['m2']
        df_final['Estoque_Total_Rolo']= df_final['Estoque_Total']/ df_final['m2']
        df_final['Importacoes_Rolo']  = df_final['Importacoes']  / df_final['m2']
        df_final['Pedidos_Rolo']      = df_final['Pedidos']      / df_final['m2']
        df_final['Saldo_Rolo']        = df_final['Saldo']        / df_final['m2']

        conn.close()
        return df_final

    except Exception as e:
        st.error(f"Erro ao carregar os dados consolidados: {e}")
        return pd.DataFrame()

# --- LÓGICA PRINCIPAL DA PÁGINA ---
st.sidebar.header("Filtros de Data")
ano_atual = datetime.now().year
ano_selecionado = st.sidebar.selectbox(
    "Selecione o Ano", options=range(ano_atual - 2, ano_atual + 3), index=2
)

nomes_meses_pt = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
                  7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
meses_disponiveis = list(range(1, 13))
meses_selecionados = st.sidebar.multiselect(
    "Selecione o(s) Mês(es)", options=meses_disponiveis,
    format_func=lambda mes: nomes_meses_pt[mes], default=meses_disponiveis
)

# MUDANÇA: Adiciona verificação para evitar carregar dados se nenhum mês for selecionado.
if not meses_selecionados:
    st.warning("Por favor, selecione pelo menos um mês para exibir os dados.")
    st.stop()

df_saldos = carregar_dados_saldos(ano_selecionado, meses_selecionados)

if df_saldos.empty:
    st.warning("Nenhum dado para exibir. Verifique os filtros ou se os arquivos foram carregados.")
else:
    st.write("---")
    st.radio("Visualizar em:", ('m2', 'Rolo'), key='unidade_saldos', horizontal=True)

    termo_pesquisa_input = st.text_input(
        "Pesquisar por Cód. Produto ou Descrição (separe por vírgula)",
        placeholder="Ex: 1020, fita (encontra itens com '1020' OU 'fita')"
    )

    df_filtrado = df_saldos.copy()
    if termo_pesquisa_input:
        df_filtrado['CodPro'] = df_filtrado['CodPro'].astype(str)
        df_filtrado['Descricao'] = df_filtrado['Descricao'].astype(str)
        termos_pesquisa = [termo.strip().lower() for termo in termo_pesquisa_input.split(',') if termo.strip()]
        
        # MUDANÇA: Lógica de pesquisa para OU (OR) em vez de E (AND)
        # Inicia a máscara como False e ativa se qualquer termo corresponder.
        mascara_final = pd.Series(False, index=df_filtrado.index)
        for termo in termos_pesquisa:
            mascara_termo = (
                df_filtrado['CodPro'].str.contains(termo, case=False, na=False) |
                df_filtrado['Descricao'].str.contains(termo, case=False, na=False)
            )
            mascara_final |= mascara_termo # Usando |= (OU)
        df_filtrado = df_filtrado[mascara_final]

    if df_filtrado.empty:
        st.info("Nenhum item encontrado para os filtros e pesquisa selecionados.")
    else:
        # MUDANÇA: Lógica de unidade refatorada para evitar repetição.
        # Define o sufixo da coluna e o rótulo com base na seleção do usuário.
        if st.session_state.unidade_saldos == 'm2':
            suffix = ''
            label_unidade = "(m²)"
        else:
            suffix = '_Rolo'
            label_unidade = "(Rolos)"

        # Calcula os KPIs usando o sufixo dinâmico.
        total_itens = df_filtrado['CodPro'].nunique()
        total_estoque = df_filtrado[f'Estoque_Total{suffix}'].sum()
        total_import  = df_filtrado[f'Importacoes{suffix}'].sum()
        total_pedido  = df_filtrado[f'Pedidos{suffix}'].sum()
        total_saldo   = df_filtrado[f'Saldo{suffix}'].sum()
        total_h1 = df_filtrado[f'Estoque_1{suffix}'].sum()
        total_h3 = df_filtrado[f'Estoque_3{suffix}'].sum()
        total_h19= df_filtrado[f'Estoque_19{suffix}'].sum()

        # Exibe os KPIs.
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            with st.container(border=True):
                st.metric(label="Total Itens", value=f"{total_itens:,}".replace(",", "."))
        with col2:
            with st.container(border=True):
                st.metric(label=f"Total Estoque {label_unidade}", value=formatar_inteiro(total_estoque))
        with col3:
            with st.container(border=True):
                st.metric(label=f"Total Import. {label_unidade}", value=formatar_inteiro(total_import))
        with col4:
            with st.container(border=True):
                st.metric(label=f"Total Pedidos {label_unidade}", value=formatar_inteiro(total_pedido))
        with col5:
            with st.container(border=True):
                st.metric(label=f"Saldo Final {label_unidade}", value=formatar_inteiro(total_saldo), delta_color="off")

        with st.expander(f"Detalhe do Estoque por Hub {label_unidade}", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Hub1", formatar_inteiro(total_h1))
            c2.metric("Hub3", formatar_inteiro(total_h3))
            c3.metric("Hub19", formatar_inteiro(total_h19))

        st.write("---")
        st.subheader("Visão Consolidada de Saldos (por Hub)")

        # MUDANÇA: Define as colunas a exibir e os nomes de forma dinâmica.
        colunas_para_exibir = [
            'CodPro', 'Descricao',
            f'Estoque_1{suffix}', f'Estoque_3{suffix}', f'Estoque_19{suffix}', f'Estoque_Total{suffix}',
            f'Importacoes{suffix}', f'Pedidos{suffix}', f'Saldo{suffix}'
        ]
        col_renome = {
            'CodPro': 'Cód. Produto', 'Descricao': 'Descrição',
            f'Estoque_1{suffix}': 'Hub1', f'Estoque_3{suffix}': 'Hub3', f'Estoque_19{suffix}': 'Hub19',
            f'Estoque_Total{suffix}': 'Estoque Total', f'Importacoes{suffix}': 'Importações',
            f'Pedidos{suffix}': 'Pedidos', f'Saldo{suffix}': 'Saldo'
        }

        df_para_exibir = df_filtrado[colunas_para_exibir].rename(columns=col_renome)

        st.dataframe(
            df_para_exibir,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Hub1": st.column_config.NumberColumn(format="%.0f"),
                "Hub3": st.column_config.NumberColumn(format="%.0f"),
                "Hub19": st.column_config.NumberColumn(format="%.0f"),
                "Estoque Total": st.column_config.NumberColumn(format="%.0f"),
                "Importações": st.column_config.NumberColumn(format="%.0f"),
                "Pedidos": st.column_config.NumberColumn(format="%.0f"),
                "Saldo": st.column_config.NumberColumn(format="%.0f"),
            }
        )