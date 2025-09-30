import streamlit as st
import streamlit_authenticator as stauth
import sqlite3
import pandas as pd
import bcrypt # Importa a biblioteca para criptografia

st.set_page_config(page_title="Gestor", page_icon="📊", layout="wide")

DB_FILE = "gestor_mkt.db"

# --- FUNÇÃO DE INICIALIZAÇÃO DO BANCO DE DADOS ---
def initialize_database():
    """
    Cria as tabelas do banco de dados se não existirem
    e adiciona um usuário 'master' padrão se a tabela de usuários estiver vazia.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Cria todas as tabelas necessárias com a cláusula "IF NOT EXISTS"
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY, name TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permissoes (
            role TEXT NOT NULL, page_name TEXT NOT NULL, PRIMARY KEY (role, page_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            codpro TEXT, produto TEXT, qtde REAL, deposito TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imports (
            nome TEXT, Data_prevista TEXT, CodPro TEXT, Descricao TEXT, Rolos REAL, 
            M2 REAL, Status_fabrica TEXT, Recebido TEXT, reservado TEXT
        )
    """)
    # (Adicione outros CREATE TABLE IF NOT EXISTS para as demais tabelas se necessário)

    # Verifica se a tabela de usuários está vazia
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        # Se estiver vazia, cria um usuário 'master' com senha '123'
        st.warning("Nenhum usuário encontrado. Criando usuário 'master' com senha '123'. Altere esta senha no primeiro login.")
        hashed_password = bcrypt.hashpw('123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute(
            "INSERT INTO usuarios (username, name, password, role) VALUES (?, ?, ?, ?)",
            ('master', 'Usuário Master', hashed_password, 'Master')
        )

    conn.commit()
    conn.close()
# --- FIM DA FUNÇÃO DE INICIALIZAÇÃO ---


# --- CHAMA A FUNÇÃO DE INICIALIZAÇÃO NO INÍCIO DA EXECUÇÃO ---
initialize_database()


# --- FUNÇÃO PARA MOSTRAR O CONTEÚDO DA PÁGINA INICIAL ---
def show_home_page():
    st.title(f'Bem-vindo ao Gestor, {st.session_state["name"]}!')
    st.write(f'Seu perfil de acesso é: **{st.session_state["role"]}**')

# --- MAPEAMENTO DE TODAS AS PÁGINAS DO APLICATIVO (ORDEM ATUALIZADA) ---
ALL_PAGES = {
    "app": st.Page(show_home_page, title="Início", icon="🏠", default=True),
    "1_Vendas": st.Page("pages/1_Vendas.py", title="Vendas", icon="💰"),
    "2_Pedidos": st.Page("pages/2_Pedidos.py", title="Pedidos", icon="📦"),
    "3_Marketing": st.Page("pages/3_Marketing.py", title="Marketing", icon="🚀"),
    "4_Estoque": st.Page("pages/4_Estoque.py", title="Estoque", icon="📦"),
    "5_Importacoes": st.Page("pages/5_Imports.py", title="Importações", icon="🚢"),
    "6_Saldos": st.Page("pages/6_Saldos.py", title="Saldos", icon="⚖️"),
    "7_Conexao_Contatos": st.Page("pages/7_Conexao_Contatos.py", title="Conexão de Contatos", icon="🔗"),
    "8_Suri_Sync": st.Page("pages/8_Suri_Sync.py", title="Sincronizar Suri", icon="🔄"),
    "9_Tabelas": st.Page("pages/9_Tabelas.py", title="Tabelas", icon="📚"),
    "10_Uploads": st.Page("pages/10_Uploads.py", title="Uploads", icon="📤"),
    "11_Gerenciamento": st.Page("pages/11_Gerenciamento.py", title="Gerenciamento", icon="🔐"),
}


# --- FUNÇÕES DE BANCO DE DADOS (sem alterações) ---
@st.cache_resource(ttl=300)
def fetch_users():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        df_users = pd.read_sql_query("SELECT * FROM usuarios", conn)
        conn.close()
    except Exception:
        return {"usernames": {}}, {}
    credentials = {"usernames": {}}
    for _, row in df_users.iterrows():
        credentials["usernames"][row['username']] = { "name": row['name'], "password": row['password'] }
    user_roles = pd.Series(df_users.role.values, index=df_users.username).to_dict()
    return credentials, user_roles

@st.cache_data(ttl=300)
def get_user_permissions_from_db(_role):
    if not _role: return []
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        df_perms = pd.read_sql_query("SELECT page_name FROM permissoes WHERE role = ?", conn, params=(_role,))
        conn.close()
        return df_perms['page_name'].tolist()
    except: return []

# --- FUNÇÃO DE VERIFICAÇÃO (sem alterações) ---
def ensure_permissions_loaded():
    if not st.session_state.get("authentication_status"):
        return
    is_loaded_for_correct_user = (
        "permissions" in st.session_state and
        st.session_state.get("_user_for_permissions") == st.session_state.get("username")
    )
    if not is_loaded_for_correct_user:
        username = st.session_state.get("username")
        role = user_roles.get(username)
        permissions = get_user_permissions_from_db(role)
        st.session_state["role"] = role
        st.session_state["permissions"] = permissions
        st.session_state["_user_for_permissions"] = username

# --- LÓGICA DE LOGIN ---
credentials, user_roles = fetch_users()
# A verificação de erro crítico agora acontece após a inicialização, então é mais segura
if not credentials or not credentials.get("usernames"):
    st.error("ERRO CRÍTICO: Nenhum usuário encontrado no banco de dados. Tente recarregar a página.")
    st.stop()
authenticator = stauth.Authenticate(credentials, "gestor_mkt_cookie", "abcdef", 0)

# --- NAVEGAÇÃO DINÂMICA E LÓGICA DE PÁGINA ---
if not st.session_state.get("authentication_status"):
    _, col2, _ = st.columns(3)
    with col2:
         authenticator.login(fields={'Form name': 'Gestor'})
    if st.session_state.get("authentication_status") is False:
        st.error("Usuário ou senha incorretos.")
    st.stop()

# --- SE O USUÁRIO ESTIVER LOGADO ---
ensure_permissions_loaded()

pages_to_show = []
if st.session_state.get("role") == "Master":
    pages_to_show = list(ALL_PAGES.values())
else:
    allowed_keys = st.session_state.get("permissions", [])
    pages_to_show.append(ALL_PAGES["app"])
    for key, page in ALL_PAGES.items():
        if key in allowed_keys:
            pages_to_show.append(page)

pg = st.navigation(pages_to_show)

with st.sidebar:
    st.divider()
    st.subheader(f'Bem-vindo, {st.session_state["name"]}!')
    
    if authenticator.logout("Logout", "main"):
        st.cache_data.clear()
        st.cache_resource.clear()
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

pg.run()