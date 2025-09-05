# pages/4_🚢_Importacao.py

import streamlit as st
import pandas as pd
import sqlite3
import locale
from datetime import datetime

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
# Checa se o usuário está logado
if not st.session_state.get("logged_in", False):
    st.error("Por favor, faça o login para acessar esta página.")
    st.stop()


# --- CONFIGURAÇÕES DA PÁGINA E TÍTULO ---
st.set_page_config(layout="wide")

# Configura o locale para português do Brasil para obter nomes dos meses corretamente
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    st.warning("Não foi possível configurar o idioma para Português. Os nomes dos meses podem aparecer em inglês.")

# --- FUNÇÕES DE BANCO DE DADOS E CARREGAMENTO ---

@st.cache_data
def carregar_dados_importacao():
    """
    Carrega e prepara os dados de importação para análise.
    """
    try:
        conn = sqlite3.connect('gestor.db')
        query = """
        SELECT
            i.Nome_Importacao, i.Previsao_Chegada, i.CodPro,
            i.Descricao AS Descricao_Produto, i.M2, i.Status_Fabrica,
            i.Recebido, i.Reservado,
            p.m2 AS m2_produto_base
        FROM importacoes i
        LEFT JOIN produtos p ON i.CodPro = p.CodPro;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        # Tratamento de dados
        df['Previsao_Chegada'] = pd.to_datetime(df['Previsao_Chegada'], errors='coerce')
        df.dropna(subset=['Previsao_Chegada'], inplace=True)
        
        for col in ['Status_Fabrica', 'Recebido', 'Reservado', 'Descricao_Produto']:
            df[col] = df[col].fillna('N/A')

        df['Ano'] = df['Previsao_Chegada'].dt.year
        df['Mes_Num'] = df['Previsao_Chegada'].dt.month
        df['Mes_Nome'] = df['Previsao_Chegada'].dt.strftime('%B').str.capitalize()
        
        df['m2_produto_base'] = pd.to_numeric(df['m2_produto_base'], errors='coerce').fillna(1)
        df.loc[df['m2_produto_base'] == 0, 'm2_produto_base'] = 1
        
        df['M2'] = pd.to_numeric(df['M2'], errors='coerce').fillna(0)

        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados de importação: {e}")
        return pd.DataFrame()

# --- CARREGAMENTO INICIAL DOS DADOS ---
df_import = carregar_dados_importacao()

# --- BARRA LATERAL DE FILTROS ---
st.sidebar.header("Filtros")

if df_import.empty:
    st.warning("Não há dados de importação para exibir. Carregue o arquivo `imports.xlsx` na página '💾 Dados'.")
else:
    # Filtros da barra lateral
    ano_selecionado = st.sidebar.selectbox("Ano", sorted(df_import['Ano'].unique(), reverse=True))
    
    # --- ALTERAÇÃO PARA SELEÇÃO MÚLTIPLA DE MÊS ---
    mes_atual = datetime.now().month
    lista_meses = {datetime(2000, i, 1).strftime("%B").capitalize(): i for i in range(1, 13)}
    
    meses_selecionados_nomes = st.sidebar.multiselect(
        "Meses", 
        options=list(lista_meses.keys()), 
        default=datetime(2000, mes_atual, 1).strftime("%B").capitalize()
    )
    # Converte nomes dos meses selecionados para números
    meses_selecionados_numeros = [lista_meses[nome] for nome in meses_selecionados_nomes]

    status_disponiveis = sorted(df_import['Status_Fabrica'].unique())
    status_padrao = [s for s in status_disponiveis if s.lower() != 'não atendido']
    status_selecionado = st.sidebar.multiselect("Status Fábrica", status_disponiveis, default=status_padrao)

    recebido_opcoes = sorted(df_import['Recebido'].unique())
    recebido_padrao = 'não' if 'não' in recebido_opcoes else recebido_opcoes[0]
    recebido_selecionado = st.sidebar.selectbox("Recebido", recebido_opcoes, index=recebido_opcoes.index(recebido_padrao))

    reservado_opcoes = sorted(df_import['Reservado'].unique())
    reservado_padrao = 'não' if 'não' in reservado_opcoes else reservado_opcoes[0]
    reservado_selecionado = st.sidebar.selectbox("Reservado", reservado_opcoes, index=reservado_opcoes.index(reservado_padrao))

    # --- LAYOUT PRINCIPAL ---
    st.title("🚢 Análise de Importações")

    unidade_visualizacao = st.radio("Unidade de Medida", ('m²', 'Rolo'), horizontal=True, key='unidade_import')
    termo_pesquisa = st.text_input("Pesquisar por Cód. Produto, Descrição ou Importação:")

    # --- LÓGICA DE FILTRAGEM E PROCESSAMENTO ---
    # Garante que a lista de meses não esteja vazia para evitar erro no filtro
    if not meses_selecionados_numeros:
        st.warning("Por favor, selecione pelo menos um mês.")
        st.stop()

    df_filtrado = df_import[
        (df_import['Ano'] == ano_selecionado) &
        (df_import['Mes_Num'].isin(meses_selecionados_numeros)) & # <-- Lógica de filtro atualizada
        (df_import['Status_Fabrica'].isin(status_selecionado)) &
        (df_import['Recebido'] == recebido_selecionado) &
        (df_import['Reservado'] == reservado_selecionado)
    ]

    if termo_pesquisa:
        df_filtrado = df_filtrado[
            df_filtrado['CodPro'].astype(str).str.contains(termo_pesquisa, case=False) |
            df_filtrado['Descricao_Produto'].str.contains(termo_pesquisa, case=False) |
            df_filtrado['Nome_Importacao'].str.contains(termo_pesquisa, case=False)
        ]

    # --- CRIAÇÃO E EXIBIÇÃO DA TABELA ---
    if df_filtrado.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
    else:
        # Define a coluna de quantidade
        if unidade_visualizacao == 'm²':
            df_filtrado['Quantidade'] = df_filtrado['M2']
        else: # Rolo
            df_filtrado['Quantidade'] = df_filtrado['M2'] / df_filtrado['m2_produto_base']

        # Agrupa os dados para a tabela final
        tabela_pivot = pd.pivot_table(
            df_filtrado,
            values='Quantidade',
            index=['Nome_Importacao', 'CodPro', 'Descricao_Produto'],
            columns='Mes_Nome',
            aggfunc='sum',
            fill_value=0
        ).reset_index()
        
        # Reordena as colunas de mês cronologicamente
        ordem_meses = [datetime(2000, i, 1).strftime('%B').capitalize() for i in range(1, 13)]
        colunas_meses_presentes = [mes for mes in ordem_meses if mes in tabela_pivot.columns]
        colunas_base = ['Nome_Importacao', 'CodPro', 'Descricao_Produto']
        tabela_pivot = tabela_pivot[colunas_base + colunas_meses_presentes]


        # Adiciona a coluna Total
        tabela_pivot['Total'] = tabela_pivot[colunas_meses_presentes].sum(axis=1)

        # Remove linhas onde o total é zero
        tabela_pivot = tabela_pivot[tabela_pivot['Total'] > 0]

        # Formatação para #.###
        colunas_para_formatar = colunas_meses_presentes + ['Total']
        format_dict = {col: lambda x: f'{int(round(x, 0)):,}'.replace(',', '.') for col in colunas_para_formatar}
        
        # Renomeia as colunas para a exibição
        tabela_pivot = tabela_pivot.rename(columns={'Nome_Importacao': 'Importação', 'Descricao_Produto': 'Descrição'})
        
        # Aplica o estilo e mostra a tabela
        st.dataframe(
            tabela_pivot.style.format(format_dict),
            use_container_width=True,
            hide_index=True
        )