import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from utils import padronizar_telefone, formatar_data
import os

# --- BLOCO DE CONTROLE DE ACESSO (sem alterações) ---
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
    if st.session_state.get("role") == "Master": return
    allowed_pages = st.session_state.get("permissions", [])
    if page_name not in allowed_pages:
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()
check_permission()
# --- FIM DO BLOCO ---

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Upload de Arquivos", page_icon="📤", layout="wide")
st.title("📤 Upload de Arquivos")
# ... (conteúdo do st.write sem alterações) ...
st.markdown("---")

# --- FUNÇÕES AUXILIARES ---
def separar_cod_e_nome(nome_completo):
    if isinstance(nome_completo, str) and '|' in nome_completo:
        partes = nome_completo.split('|', 1); return partes[0].strip(), partes[1].strip()
    else:
        nome_original = "" if pd.isna(nome_completo) else str(nome_completo); return "0", nome_original.strip()

DB_FILE = "gestor_mkt.db"
def get_db_connection(): return sqlite3.connect(DB_FILE)

# --- UPLOADER ---
uploaded_file = st.file_uploader("Selecione um arquivo", type=["csv", "xlsx", "txt", "xls"])

if uploaded_file is not None:
    conn = get_db_connection()
    file_name = uploaded_file.name

    # --- LÓGICA PARA ARQUIVO DE IMPORTAÇÃO (ATUALIZADO) ---
    if file_name == "imports.xlsx":
        st.info("Processando arquivo de importações...")
        try:
            df = pd.read_excel(uploaded_file, dtype=str, sheet_name="import")
            df.columns = df.columns.str.strip()
            
            # Adicionada a coluna 'reservado'
            colunas_esperadas = ['nome', 'Data_prevista', 'CodPro', 'Descricao', 'Rolos', 'M2', 'Status_fabrica', 'Recebido', 'reservado']
            df = df.reindex(columns=colunas_esperadas)

            df['CodPro'] = df['CodPro'].str.lstrip('0')
            df['Data_prevista'] = pd.to_datetime(df['Data_prevista'], errors='coerce').dt.strftime('%d/%m/%Y')
            df['Rolos'] = pd.to_numeric(df['Rolos'], errors='coerce').fillna(0)
            df['M2'] = pd.to_numeric(df['M2'], errors='coerce').fillna(0)

            st.subheader("Prévia dos Dados de Importação")
            st.dataframe(df.head())

            if st.button("Confirmar Importação de 'imports.xlsx'"):
                df.to_sql('imports', conn, if_exists='replace', index=False)
                st.success("Dados de importação salvos com sucesso!")

        except Exception as e:
            st.error(f"Erro ao processar o arquivo '{file_name}': {e}")
    
    # ... (o restante do código para os outros arquivos permanece exatamente o mesmo) ...
    # --- LÓGICA PARA ARQUIVOS DE ESTOQUE ---
    elif file_name in ["hub1.txt", "hub3.txt", "hub19.txt"]:
        deposito = file_name.split('.')[0]
        st.info(f"Processando arquivo de estoque para o depósito '{deposito}'...")
        try:
            cursor = conn.cursor()
            st.write(f"Deletando registros de estoque antigos para '{deposito}'...")
            cursor.execute("DELETE FROM estoque WHERE deposito = ?", (deposito,))
            conn.commit()
            df = pd.read_csv(uploaded_file, header=None, skiprows=2, encoding='latin-1', skip_blank_lines=True, sep='\t')
            if df.empty:
                raise ValueError("O arquivo de estoque está vazio ou em formato não reconhecido.")
            df.rename(columns={0: 'raw'}, inplace=True)
            df.dropna(subset=['raw'], inplace=True)
            df = df[~df['raw'].str.contains('TOTAL GERAL', na=False)]
            df['codpro'] = df['raw'].str.slice(18, 24).str.strip()
            df['produto'] = df['raw'].str.slice(25, 75).str.strip()
            df['qtde'] = df['raw'].str.slice(79, 90).str.strip()
            df = df[['codpro', 'produto', 'qtde']]
            df = df.dropna(subset=['codpro'])
            df = df[df['codpro'] != '']
            df['deposito'] = deposito
            df['codpro'] = df['codpro'].str.lstrip('0')
            df['qtde'] = pd.to_numeric(df['qtde'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False), errors='coerce').fillna(0).astype(int)
            st.subheader("Prévia dos Dados de Estoque a Serem Importados")
            st.dataframe(df.head())
            if st.button(f"Confirmar Importação para '{deposito}'"):
                df.to_sql('estoque', conn, if_exists='append', index=False)
                st.success(f"Dados de estoque para '{deposito}' importados com sucesso!")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo '{file_name}': {e}")
    # --- LÓGICA PARA ATUALIZAR VENDAS DO MÊS ---
    elif file_name == "vendas.txt":
        st.info("Arquivo 'vendas.txt' recebido. Atualizando vendas do mês atual...")
        try:
            hoje = datetime.now()
            ano_atual, mes_atual = str(hoje.year), str(hoje.month).zfill(2)
            st.write(f"Deletando registros de vendas existentes para {mes_atual}/{ano_atual}...")
            cursor = conn.cursor()
            sql_delete = "DELETE FROM vendas WHERE strftime('%Y', substr(Data_NF, 7, 4) || '-' || substr(Data_NF, 4, 2) || '-' || substr(Data_NF, 1, 2)) = ? AND strftime('%m', substr(Data_NF, 7, 4) || '-' || substr(Data_NF, 4, 2) || '-' || substr(Data_NF, 1, 2)) = ?"
            cursor.execute(sql_delete, (ano_atual, mes_atual))
            conn.commit()
            st.write("Registros antigos do mês deletados com sucesso.")
            df_bruto = pd.read_csv(uploaded_file, encoding='latin-1', sep=';', skipinitialspace=True)
            df_bruto.columns = df_bruto.columns.str.strip()
            colunas = ['Data_NF', 'Num_NF', 'Codcli', 'Nome_do_Cliente', 'UF', 'Codpro', 'QtdeFaturada', 'Vlr_Unitario', 'Valor_Total', 'Vend', 'Empresa']
            df = df_bruto[colunas].copy()
            for col in ['QtdeFaturada', 'Vlr_Unitario', 'Valor_Total']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df['Data_NF'] = formatar_data(df['Data_NF'])
            for col in ['Codcli', 'Codpro', 'Num_NF', 'Vend']:
                df[col] = df[col].astype(str).str.lstrip('0')
            st.subheader("Prévia dos Dados a Serem Adicionados")
            st.dataframe(df.head())
            if st.button("Confirmar Atualização de Vendas"):
                df.to_sql('vendas', conn, if_exists='append', index=False)
                st.success(f"Dados de vendas para {mes_atual}/{ano_atual} atualizados com sucesso!")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo 'vendas.txt': {e}")
    # --- LÓGICA PARA HISTÓRICO DE VENDAS ---
    elif file_name.startswith("lucratividade"):
        st.info(f"Arquivo de histórico '{file_name}' recebido. Processando...")
        try:
            df_bruto = pd.read_csv(uploaded_file, encoding='latin-1', sep=';', skipinitialspace=True)
            df_bruto.columns = df_bruto.columns.str.strip()
            colunas = ['Data_NF', 'Num_NF', 'Codcli', 'Nome_do_Cliente', 'UF', 'Codpro', 'QtdeFaturada', 'Vlr_Unitario', 'Valor_Total', 'Vend', 'Empresa']
            df = df_bruto[colunas].copy()
            for col in ['QtdeFaturada', 'Vlr_Unitario', 'Valor_Total']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df['Data_NF'] = formatar_data(df['Data_NF'])
            for col in ['Codcli', 'Codpro', 'Num_NF', 'Vend']:
                df[col] = df[col].astype(str).str.lstrip('0')
            st.subheader("Prévia dos Dados")
            st.dataframe(df.head())
            if st.button("Confirmar Importação para 'vendas'"):
                df.to_sql('vendas', conn, if_exists='replace', index=False)
                st.success("Dados de 'vendas' importados com sucesso!")
        except Exception as e: st.error(f"Erro: {e}")
    # --- LÓGICA PARA PRODUTOS ---
    elif file_name == "produtos.csv":
        st.info("Processando 'produtos.csv'...")
        try:
            df = pd.read_csv(uploaded_file, encoding='latin-1', sep=';', dtype=str)
            df.columns = df.columns.str.strip()
            if 'codpro' in df.columns: df['codpro'] = df['codpro'].str.lstrip('0')
            if 'm2' in df.columns:
                df['m2'] = df['m2'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                df['m2'] = pd.to_numeric(df['m2'], errors='coerce')
            st.subheader("Prévia dos Dados")
            st.dataframe(df.head())
            if st.button("Confirmar Importação para 'produtos'"):
                df.to_sql('produtos', conn, if_exists='replace', index=False)
                st.success("Dados de 'produtos' importados com sucesso!")
        except Exception as e: st.error(f"Erro ao processar 'produtos.csv': {e}")
    # --- LÓGICA PARA CLIENTES ---
    elif file_name == "clientes.csv":
        st.info("Processando 'clientes.csv'...")
        try:
            df = pd.read_csv(uploaded_file, encoding='utf-8-sig', sep=';', header=0, names=['Codigo', 'Nome', 'Tipo_Pessoa', 'Email', 'Estado', 'Cidade', 'Fone', 'Segmento', 'Vendedor', 'Representante', 'Situacao', 'Tipo_Fiscal', 'Papeis', 'Tags'])
            df['Fone'] = df['Fone'].astype(str).apply(padronizar_telefone)
            df['Codigo'] = df['Codigo'].astype(str).str.lstrip('0')
            st.subheader("Prévia dos Dados")
            st.dataframe(df.head())
            if st.button("Confirmar Importação para 'clientes'"):
                df.to_sql('clientes', conn, if_exists='replace', index=False)
                st.success("Dados de 'clientes' importados com sucesso!")
        except Exception as e: st.error(f"Erro ao processar 'clientes.csv': {e}")
    # --- LÓGICA PARA PEDIDOS ---
    elif file_name in ["pedidos_cd.xls", "pedidos_loja.xls"]:
        empresa_id = '1' if file_name == "pedidos_cd.xls" else '3'
        st.info(f"Processando pedidos da Empresa {empresa_id}...")
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pedidos WHERE Empresa = ?", (empresa_id,))
            conn.commit()
            df = pd.read_excel(uploaded_file)
            mapa_colunas = {
                'PEDVENDCAB_tipo': 'Tipo', 'PEDVENDCAB_numped': 'Num_Ped', 'PEDVENDCAB_dtpedido': 'Dt_Pedido', 'PEDVENDCAB_dtentrega': 'Dt_Entrega',
                'PEDVENDCAB_codcli': 'Codcli', 'PEDVENDCAB_nomecli': 'Nome_Cli', 'PEDVENDITE_codpro': 'Codpro', 'PEDVENDITE_descricao': 'Descricao_Produto',
                'PEDVENDITE_qtvend': 'Qt_Vend', 'PEDVENDITE_vlunit': 'Vlr_Unit', 'PEDVENDITE_vlliquido': 'Vlr_Liquido', 'PEDVENDITE_ocompra': 'OC',
                'PEDVENDITE_vendedor': 'Cod_Vend', 'TBVEND_nome': 'Nome_Vend', 'PEDVENDCAB_numpedweb': 'Num_Ped_Web', 'PEDVENDCAB_empresa': 'Empresa'
            }
            df = df.rename(columns=mapa_colunas)
            df['Empresa'] = empresa_id
            df['Dt_Pedido'] = formatar_data(df['Dt_Pedido'])
            df['Dt_Entrega'] = formatar_data(df['Dt_Entrega'])
            for col in ['Num_Ped', 'Codcli', 'Codpro', 'Cod_Vend']:
                if col in df.columns: df[col] = df[col].astype(str).str.lstrip('0')
            st.subheader("Prévia dos Dados")
            st.dataframe(df.head())
            if st.button(f"Confirmar Importação para 'pedidos' (Empresa {empresa_id})"):
                df.to_sql('pedidos', conn, if_exists='append', index=False)
                st.success(f"Dados importados com sucesso!")
        except Exception as e: st.error(f"Erro: {e}")
    # --- LÓGICA PARA SURI ---
    elif file_name == "suri.xlsx":
        st.info("Processando 'suri.xlsx'...")
        try:
            df = pd.read_excel(uploaded_file)
            df.columns = df.columns.str.strip()
            mapa_nomes = {'Número': 'Numero', 'Documento de Identificação': 'Documento_Identificacao', 'Gênero': 'Genero', 'Id do Canal': 'Id_Canal', 'Tipo do Canal': 'Tipo_Canal', 'Primeiro Contato': 'Primeiro_Contato', 'Observação': 'Observacao'}
            df = df.rename(columns=mapa_nomes)
            df[['codcli', 'Nome']] = df['Nome'].apply(lambda x: pd.Series(separar_cod_e_nome(x)))
            df['codcli'] = df['codcli'].astype(str)
            df['Numero'] = df['Numero'].astype(str).apply(padronizar_telefone)
            df['Primeiro_Contato'] = formatar_data(df['Primeiro_Contato'])
            st.subheader("Prévia dos Dados")
            st.dataframe(df.head())
            if st.button("Confirmar Importação para 'suri'"):
                df.to_sql('suri', conn, if_exists='replace', index=False)
                st.success("Dados de 'suri' importados com sucesso!")
        except Exception as e: st.error(f"Erro: {e}")
    # --- LÓGICA PARA RD ---
    elif file_name == "RD.csv":
        st.info("Processando 'RD.csv'...")
        try:
            nomes_colunas_rd = ['Email', 'Nome', 'Telefone', 'Celular', 'Empresa', 'Estado', 'Total_conversoes', 'Data_primeira_conversao', 'Origem_primeira_conversao', 'Data_ultima_conversao', 'Origem_ultima_conversao', 'CNPJ', 'CodigoCliente']
            df = pd.read_csv(uploaded_file, encoding='latin-1', sep=';', header=0, names=nomes_colunas_rd)
            df['Telefone'] = df['Telefone'].astype(str).apply(padronizar_telefone)
            df['Celular'] = df['Celular'].astype(str).apply(padronizar_telefone)
            df['Data_primeira_conversao'] = formatar_data(df['Data_primeira_conversao'])
            df['Data_ultima_conversao'] = formatar_data(df['Data_ultima_conversao'])
            st.subheader("Prévia dos Dados")
            st.dataframe(df.head())
            if st.button("Confirmar Importação para 'rd'"):
                df.to_sql('rd', conn, if_exists='replace', index=False)
                st.success("Dados de 'rd' importados com sucesso!")
        except Exception as e: st.error(f"Erro ao processar 'RD.csv': {e}")
    # --- ARQUIVO NÃO RECONHECIDO ---
    else:
        st.error(f"Arquivo não reconhecido: '{file_name}'. Verifique o nome e a extensão.")

    conn.close()
else:
    st.info("Aguardando o envio de um arquivo.")