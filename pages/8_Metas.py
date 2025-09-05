# pages/7_🎯_Metas.py

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
st.title("🎯 Análise de Metas")

# --- FUNÇÕES ---
def criar_conexao():
    return sqlite3.connect('gestor.db')

def formatar_real(valor):
    """Formata um número para o padrão R$ #.###"""
    try:
        return f"R$ {valor:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "R$ 0"

def formatar_percentual(valor):
    """Formata um número para o padrão #.###,##%"""
    try:
        valor_formatado = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{valor_formatado}%"
    except (ValueError, TypeError):
        return "0,00%"

def colorir_negativos(valor):
    """Colore o texto de vermelho se o valor for um número negativo."""
    cor = 'red' if isinstance(valor, (int, float)) and valor < 0 else ''
    return f'color: {cor}'

def colorir_percentual_meta(coluna):
    """Aplica a cor vermelha em valores < 100 apenas na coluna '% Meta'."""
    # A coluna tem um MultiIndex (ex: ('Jan', '% Meta')). Acessamos o nome pelo índice 1.
    if coluna.name[1] == '% Meta': 
        return ['color: red' if valor < 100 else '' for valor in coluna]
    return ['' for _ in coluna] # Não aplica cor nas outras colunas

@st.cache_data
def carregar_dados_consolidados():
    """Carrega, processa e une as tabelas de metas e vendas usando o CodCli como chave."""
    try:
        conn = criar_conexao()
        
        df_metas_raw = pd.read_sql_query("SELECT CodCli, Cliente, Vendedor, Data, Valor FROM metas", conn)
        df_vendas_raw = pd.read_sql_query("SELECT Codcli, Nome_do_Cliente, Nome_do_Vendedor, Data_NF, QtdeFaturada, Vlr_Unitario FROM vendas", conn)
        conn.close()

        # --- Processa Metas ---
        df_metas = df_metas_raw.copy()
        df_metas['Data'] = pd.to_datetime(df_metas['Data'], errors='coerce', dayfirst=True)
        df_metas.dropna(subset=['Data', 'CodCli'], inplace=True)
        df_metas['Ano'] = df_metas['Data'].dt.year
        df_metas['Mes'] = df_metas['Data'].dt.month
        df_metas.rename(columns={'Valor': 'Meta'}, inplace=True)
        for col in ['Vendedor', 'CodCli']:
            df_metas[col] = df_metas[col].astype(str).str.strip().str.upper()
        df_metas['Cliente'] = df_metas['Cliente'].str.strip().str.upper()
        
        metas_agg = df_metas.groupby(['Ano', 'Mes', 'Vendedor', 'CodCli']).agg(
            Meta=('Meta', 'sum'),
            Cliente=('Cliente', 'first') # Usa o nome da meta como o "oficial"
        ).reset_index()

        # --- Processa Vendas ---
        df_vendas = df_vendas_raw.copy()
        df_vendas.rename(columns={'Nome_do_Vendedor': 'Vendedor', 'Codcli': 'CodCli'}, inplace=True)
        df_vendas['Data_NF'] = pd.to_datetime(df_vendas['Data_NF'], errors='coerce')
        df_vendas.dropna(subset=['Data_NF', 'CodCli'], inplace=True)
        df_vendas['Ano'] = df_vendas['Data_NF'].dt.year
        df_vendas['Mes'] = df_vendas['Data_NF'].dt.month
        df_vendas['Venda'] = df_vendas['QtdeFaturada'] * df_vendas['Vlr_Unitario']
        for col in ['Vendedor', 'CodCli']:
            df_vendas[col] = df_vendas[col].astype(str).str.strip().str.upper()
        
        vendas_agg = df_vendas.groupby(['Ano', 'Mes', 'Vendedor', 'CodCli'])['Venda'].sum().reset_index()

        # --- Une as tabelas usando CodCli ---
        df_final = pd.merge(metas_agg, vendas_agg, on=['Ano', 'Mes', 'Vendedor', 'CodCli'], how='outer').fillna(0)
        
        # Preenche nomes de clientes que só existem nas vendas
        df_nomes_vendas = df_vendas_raw.rename(columns={'Codcli':'CodCli', 'Nome_do_Cliente':'Cliente_Venda'})
        df_nomes_vendas['CodCli'] = df_nomes_vendas['CodCli'].astype(str).str.strip().str.upper()
        df_nomes_unicos = df_nomes_vendas.drop_duplicates(subset=['CodCli'])[['CodCli', 'Cliente_Venda']]
        
        df_final = pd.merge(df_final, df_nomes_unicos, on='CodCli', how='left')
        df_final['Cliente'] = df_final['Cliente'].replace(0, None).fillna(df_final['Cliente_Venda'])
        df_final.drop(columns=['Cliente_Venda'], inplace=True)
        
        df_final['Gap'] = df_final['Venda'] - df_final['Meta']
        df_final['% Meta'] = df_final.apply(lambda row: (row['Venda'] / row['Meta']) * 100 if row['Meta'] > 0 else 0, axis=1)

        return df_final, df_metas
        
    except Exception as e:
        st.error(f"Erro ao carregar os dados: {e}")
        return pd.DataFrame(), pd.DataFrame()

# --- LÓGICA PRINCIPAL DA PÁGINA ---
placeholder_cards = st.empty()
df_final, df_metas_base = carregar_dados_consolidados()

if df_final.empty:
    st.warning("Não foi possível carregar os dados. Verifique a página 'Dados'.")
else:
    st.sidebar.header("Filtros")
    
    anos_disponiveis = sorted(df_final['Ano'].unique().astype(int))
    ano_selecionado = st.sidebar.selectbox("Ano", options=anos_disponiveis, index=len(anos_disponiveis)-1)

    nomes_meses_pt = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
    meses_disponiveis = sorted(df_final[df_final['Ano']==ano_selecionado]['Mes'].unique().astype(int))
    meses_selecionados = st.sidebar.multiselect("Mês(es)", options=meses_disponiveis, format_func=lambda m: nomes_meses_pt[m], default=meses_disponiveis)
    
    vendedores_com_meta = sorted(df_metas_base['Vendedor'].dropna().unique())
    vendedores_selecionados = st.sidebar.multiselect("Vendedor(es) com Meta", options=vendedores_com_meta, default=vendedores_com_meta)
    
    df_filtrado = df_final[
        (df_final['Ano'] == ano_selecionado) &
        (df_final['Mes'].isin(meses_selecionados)) &
        (df_final['Vendedor'].isin(vendedores_selecionados))
    ]

    termo_pesquisa = st.text_input("Pesquisa por Vendedor, Cliente ou Cód. Cliente (separado por vírgula)")
    if termo_pesquisa:
        termos = [t.strip().upper() for t in termo_pesquisa.split(',') if t.strip()]
        for termo in termos:
            mask = (
                df_filtrado['Vendedor'].str.contains(termo, na=False) |
                df_filtrado['Cliente'].str.contains(termo, na=False) |
                df_filtrado['CodCli'].str.contains(termo, na=False)
            )
            df_filtrado = df_filtrado[mask]

    with placeholder_cards.container():
        if not df_filtrado.empty:
            clientes_distintos = df_filtrado[df_filtrado['Venda'] > 0]['Cliente'].nunique()
            meta_periodo = df_filtrado['Meta'].sum()
            realizado_periodo = df_filtrado['Venda'].sum()
            gap_periodo = realizado_periodo - meta_periodo
            percentual_meta_periodo = (realizado_periodo / meta_periodo) * 100 if meta_periodo > 0 else 0
            
            cols = st.columns(5)
            with cols[0]:
                with st.container(border=True): st.metric("Clientes (compras)", value=f"{clientes_distintos:,}".replace(",","."))
            with cols[1]:
                with st.container(border=True): st.metric("Meta", value=formatar_real(meta_periodo))
            with cols[2]:
                with st.container(border=True): st.metric("Realizado", value=formatar_real(realizado_periodo))
            with cols[3]:
                with st.container(border=True):
                    cor_gap = "red" if gap_periodo < 0 else "inherit"
                    st.markdown(f"""
                        <div style='display: flex; flex-direction: column; justify-content: center; min-height: 97px;'>
                            <div style='font-size: 0.875rem; color: #808495;'>Gap (R$)</div>
                            <div style='font-size: 1.75rem; font-weight: 600; color: {cor_gap};'>
                                {formatar_real(gap_periodo)}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            with cols[4]:
                with st.container(border=True):
                    cor_meta = "red" if percentual_meta_periodo < 100 else "inherit"
                    st.markdown(f"""
                        <div style='display: flex; flex-direction: column; justify-content: center; min-height: 97px;'>
                            <div style='font-size: 0.875rem; color: #808495;'>% Meta</div>
                            <div style='font-size: 1.75rem; font-weight: 600; color: {cor_meta};'>
                                {formatar_percentual(percentual_meta_periodo)}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
        else:
            st.write("") 

    st.write("---")
    
    if df_filtrado.empty:
        st.info("Nenhum dado encontrado para os filtros selecionados.")
    else:
        tipo_tabela = st.radio("Selecione a Tabela para Visualizar:", ("Análise de Gap (R$)", "Análise de Atendimento (%)"), horizontal=True)
        st.write("---")

        if tipo_tabela == "Análise de Gap (R$)":
            st.subheader("Análise Mensal de Gap (R$) por Cliente e Vendedor")
            valores_pivot = ['Meta', 'Venda', 'Gap']
            
            tabela_pivot = df_filtrado.pivot_table(
                index=['Cliente', 'Vendedor'], columns='Mes',
                values=valores_pivot, aggfunc='sum'
            ).fillna(0)
            
            if not tabela_pivot.empty:
                tabela_pivot = tabela_pivot.swaplevel(0, 1, axis=1).sort_index(axis=1)
                tabela_pivot.rename(columns={k: v for k, v in nomes_meses_pt.items() if k in tabela_pivot.columns.get_level_values(0)}, level=0, inplace=True)
            
            st.dataframe(
                tabela_pivot.style
                .format(formatar_real)
                .applymap(colorir_negativos)
            , use_container_width=True)

        else: # Análise de Atendimento (%)
            st.subheader("Análise Mensal de Atendimento (%) por Cliente e Vendedor")
            
            df_agg_perc = df_filtrado.groupby(['Cliente', 'Vendedor', 'Mes']).agg({'Meta': 'sum', 'Venda': 'sum'}).reset_index()
            
            meta_pivot = df_agg_perc.pivot_table(index=['Cliente', 'Vendedor'], columns='Mes', values='Meta', aggfunc='sum').fillna(0)
            venda_pivot = df_agg_perc.pivot_table(index=['Cliente', 'Vendedor'], columns='Mes', values='Venda', aggfunc='sum').fillna(0)
            
            if not meta_pivot.empty and not venda_pivot.empty:
                percentual_pivot = (venda_pivot / meta_pivot).multiply(100, fill_value=0)
                
                meta_pivot.columns = pd.MultiIndex.from_product([['Meta'], meta_pivot.columns])
                venda_pivot.columns = pd.MultiIndex.from_product([['Venda'], venda_pivot.columns])
                percentual_pivot.columns = pd.MultiIndex.from_product([['% Meta'], percentual_pivot.columns])
                
                tabela_final = pd.concat([meta_pivot, venda_pivot, percentual_pivot], axis=1)
                
                tabela_final = tabela_final.swaplevel(0, 1, axis=1).sort_index(axis=1)
                tabela_final.rename(columns={k: v for k, v in nomes_meses_pt.items() if k in tabela_final.columns.get_level_values(0)}, level=0, inplace=True)
                
                formatter = {}
                for mes_tupla in tabela_final.columns:
                    if mes_tupla[1] == '% Meta':
                        formatter[mes_tupla] = formatar_percentual
                    else:
                        formatter[mes_tupla] = formatar_real

                st.dataframe(
                    tabela_final.style
                    .format(formatter)
                    .applymap(colorir_negativos)
                    .apply(colorir_percentual_meta, axis=0)
                , use_container_width=True)