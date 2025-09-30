import streamlit as st
import pandas as pd
import sqlite3
import os
import io

# --- BLOCO DE CONTROLE DE ACESSO (Obrigatório) ---
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
    if st.session_state.get("role") == "Master":
        return

    if "permissions" not in st.session_state or st.session_state.permissions is None:
        st.session_state["permissions"] = get_user_permissions_from_db(st.session_state.get("role"))

    if page_name not in st.session_state.get("permissions", []):
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()

check_permission()
# --- FIM DO BLOCO ---


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Conexão de Contatos", page_icon="🔗", layout="wide")
st.title("🔗 Conexão e Verificação de Contatos")

# --- BOTÃO DE ATUALIZAÇÃO ---
if st.button("🔄 Atualizar Dados da Página"):
    st.cache_data.clear()
    st.toast("Os dados foram atualizados!", icon="✅")
    st.rerun()

st.markdown("---")


# --- FUNÇÕES DE APOIO ---
@st.cache_data(ttl=600)
def carregar_dados_suri(_conn):
    """Carrega os dados da tabela 'suri' e formata para o selectbox."""
    try:
        query = "SELECT codcli, Nome, telefone_suri, Numero, Ultimo_Atendente FROM suri"
        df = pd.read_sql_query(query, _conn)
        
        # Lida com valores nulos para evitar erros na formatação
        df['codcli'] = df['codcli'].fillna('N/A')
        df['Nome'] = df['Nome'].fillna('Sem Nome')
        df['telefone_suri'] = df['telefone_suri'].fillna('N/A')
        df['Numero'] = df['Numero'].fillna('N/A')
        df['Ultimo_Atendente'] = df['Ultimo_Atendente'].fillna('N/D')

        # Cria uma coluna formatada para exibição no selectbox
        df['display'] = df.apply(
            lambda row: f"{row['codcli']} | {row['Nome']} | Atendente: {row['Ultimo_Atendente']} | Fone: {row['Numero']}",
            axis=1
        )
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados da tabela 'suri': {e}")
        return pd.DataFrame()

def to_excel(df: pd.DataFrame):
    """Converte um DataFrame para um arquivo Excel em memória."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Contatos')
    processed_data = output.getvalue()
    return processed_data

# --- CONEXÃO COM O BANCO ---
DB_FILE = "gestor_mkt.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)

# --- SEÇÃO 1: INTERFACE PRINCIPAL DE BUSCA MÚLTIPLA ---
df_suri = carregar_dados_suri(conn)

if not df_suri.empty:
    opcoes_suri = df_suri['display'].tolist()

    contatos_selecionados_str = st.multiselect(
        "Pesquisar e Selecionar Contato(s) do Suri",
        options=opcoes_suri,
        help="Digite para pesquisar e selecione um ou mais contatos."
    )

    if contatos_selecionados_str:
        st.markdown("---")
        
        telefones_para_busca = set()
        for contato_str in contatos_selecionados_str:
            contato_data = df_suri[df_suri['display'] == contato_str].iloc[0]
            telefone_original = contato_data['telefone_suri']
            telefone_padronizado = contato_data['Numero']
            
            if telefone_original and telefone_original != 'N/A':
                telefones_para_busca.add(telefone_original)
            if telefone_padronizado and telefone_padronizado != 'N/A':
                telefones_para_busca.add(telefone_padronizado)
        
        lista_telefones_busca = list(telefones_para_busca)

        if not lista_telefones_busca:
            st.warning("Nenhum dos contatos selecionados possui um número de telefone válido para busca.")
        else:
            st.info(f"Buscando por número(s): **{', '.join(lista_telefones_busca)}**")

            st.subheader("Resultados na Tabela de Clientes")
            query_clientes = "SELECT * FROM clientes WHERE Fone IN ({})".format(','.join(['?']*len(lista_telefones_busca)))
            df_clientes_encontrados = pd.read_sql_query(query_clientes, conn, params=lista_telefones_busca)
            if not df_clientes_encontrados.empty:
                st.dataframe(df_clientes_encontrados, width='stretch', hide_index=True)
            else:
                st.write("Nenhum contato correspondente encontrado na tabela 'clientes'.")

            st.subheader("Resultados na Tabela RD Station")
            query_rd = "SELECT * FROM rd WHERE Celular IN ({})".format(','.join(['?']*len(lista_telefones_busca)))
            df_rd_encontrados = pd.read_sql_query(query_rd, conn, params=lista_telefones_busca)
            if not df_rd_encontrados.empty:
                st.dataframe(df_rd_encontrados, width='stretch', hide_index=True)
            else:
                st.write("Nenhum contato correspondente encontrado na tabela 'rd'.")
else:
    st.warning("A tabela 'suri' está vazia ou não pôde ser carregada. Sincronize os dados na página 'Sincronizar Suri' primeiro.")

# --- SEÇÃO 2: TABELA DE CONTATOS SURI SEM CÓDIGO DE CLIENTE ---
st.markdown("---")
st.subheader("Contatos Suri sem Código de Cliente Vinculado")
st.write("Esta tabela mostra contatos do Suri onde o `codcli` é nulo e busca correspondências em Clientes e RD.")

@st.cache_data(ttl=600)
def carregar_dados_suri_sem_codigo(_conn):
    try:
        query_suri = "SELECT Ultima_Atividade, codcli, Nome, telefone_suri, Numero, Ultimo_Atendente FROM suri WHERE codcli IS NULL OR codcli = 'N/A' OR codcli = '0'"
        df_suri_sem_codigo = pd.read_sql_query(query_suri, _conn)

        if df_suri_sem_codigo.empty:
            return pd.DataFrame()

        df_clientes_full = pd.read_sql_query("SELECT Codigo, Nome, Fone FROM clientes", _conn)
        df_rd_full = pd.read_sql_query("SELECT CodigoCliente, Nome, Celular FROM rd", _conn)

        processed_data = []
        for _, row in df_suri_sem_codigo.iterrows():
            phones_to_search = set(filter(None, [row['telefone_suri'], row['Numero']]))

            final_row = {
                'Última Atividade': row['Ultima_Atividade'],
                'Codigo': row['codcli'],
                'Nome': row['Nome'],
                'Último Atendente': row['Ultimo_Atendente'],
                'Fone_Suri': row['Numero'],
                'Cod_Cliente': None, 'Nome_Cliente': None, 'Numero_Cliente': None,
                'Cod_RD': None, 'Nome_RD': None, 'Numero_RD': None
            }

            if phones_to_search:
                match_cliente = df_clientes_full[df_clientes_full['Fone'].isin(phones_to_search)]
                if not match_cliente.empty:
                    cliente_data = match_cliente.iloc[0]
                    final_row.update({
                        'Cod_Cliente': cliente_data['Codigo'],
                        'Nome_Cliente': cliente_data['Nome'],
                        'Numero_Cliente': cliente_data['Fone']
                    })

                match_rd = df_rd_full[df_rd_full['Celular'].isin(phones_to_search)]
                if not match_rd.empty:
                    rd_data = match_rd.iloc[0]
                    final_row.update({
                        'Cod_RD': rd_data['CodigoCliente'],
                        'Nome_RD': rd_data['Nome'],
                        'Numero_RD': rd_data['Celular']
                    })
            
            processed_data.append(final_row)

        df_final = pd.DataFrame(processed_data)
        col_order = ['Última Atividade', 'Codigo', 'Nome', 'Último Atendente', 'Fone_Suri', 'Cod_Cliente', 'Nome_Cliente', 'Numero_Cliente', 'Cod_RD', 'Nome_RD', 'Numero_RD']
        for col in col_order:
            if col not in df_final.columns:
                df_final[col] = None
        return df_final[col_order]

    except Exception as e:
        st.error(f"Erro ao processar contatos sem código: {e}")
        return pd.DataFrame()

df_sem_codigo = carregar_dados_suri_sem_codigo(conn)

if not df_sem_codigo.empty:
    pesquisa = st.text_input(
        "Pesquisar na tabela abaixo (separe os termos por vírgula para busca múltipla):",
        key="pesquisa_sem_codigo"
    )
    
    df_filtrado = df_sem_codigo.copy()
    
    if pesquisa:
        termos = [term.strip().lower() for term in pesquisa.split(',') if term.strip()]
        df_str = df_filtrado.astype(str).apply(lambda x: x.str.lower())
        
        for termo in termos:
            df_filtrado = df_filtrado[df_str.apply(lambda row: row.str.contains(termo, na=False)).any(axis=1)]
            if not df_filtrado.empty:
                 df_str = df_filtrado.astype(str).apply(lambda x: x.str.lower())
            else:
                 break

    st.write(f"Exibindo **{len(df_filtrado)}** de **{len(df_sem_codigo)}** registros encontrados.")
    st.dataframe(df_filtrado, width='stretch', hide_index=True)

    if not df_filtrado.empty:
        df_excel = to_excel(df_filtrado)
        st.download_button(
            label="📥 Exportar para Excel",
            data=df_excel,
            file_name="contatos_suri_sem_codigo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("Não foram encontrados contatos no Suri com código de cliente nulo ou não definido.")


# --- FECHA A CONEXÃO ---
conn.close()