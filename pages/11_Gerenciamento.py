import streamlit as st
import sqlite3
import pandas as pd
import bcrypt
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

    # 2. Garante que as permissões estão carregadas na sessão (essencial para reloads de página)
    if "permissions" not in st.session_state or st.session_state.permissions is None:
        role = st.session_state.get("role")
        if not role: # Se o perfil não existir na sessão, busca de novo
             conn = sqlite3.connect("gestor_mkt.db", check_same_thread=False)
             username = st.session_state.get("username")
             df_user = pd.read_sql_query(f"SELECT role FROM usuarios WHERE username = '{username}'", conn)
             conn.close()
             if not df_user.empty:
                 role = df_user.iloc[0]['role']
                 st.session_state["role"] = role
        st.session_state["permissions"] = get_user_permissions_from_db(role)

    # 3. Executa a verificação
    page_name = os.path.splitext(os.path.basename(__file__))[0]
    
    # O perfil Master sempre tem acesso
    if st.session_state.get("role") == "Master":
        return
        
    allowed_pages = st.session_state.get("permissions", [])
    if page_name not in allowed_pages:
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()

check_permission()
# --- FIM DO NOVO BLOCO ---
# --- FIM DO BLOCO ---

st.set_page_config(page_title="Gerenciamento de Acesso", layout="wide")
st.title("🔐 Gerenciamento de Acesso")

DB_FILE = "gestor_mkt.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)

ROLES = ["Master", "Diretor", "Gerente", "Vendedor", "Representante"]
PAGES = sorted([file.replace(".py", "") for file in os.listdir("pages") if file.endswith(".py") and not file.startswith("0_")])

tab1, tab2, tab3 = st.tabs(["🔑 Gerenciar Permissões", "👤 Criar Usuário", "📋 Listar / Excluir Usuários"])

with tab1:
    st.subheader("Definir Acesso das Páginas por Perfil")
    perfil_selecionado = st.selectbox("Selecione o perfil para editar", ROLES)

    if perfil_selecionado:
        if perfil_selecionado == "Master":
            st.info("O perfil Master tem acesso total e irrestrito a todas as páginas. Esta configuração não pode ser alterada.")
            st.warning("A página de Gerenciamento não pode ser atribuída a outros perfis por aqui.")
        
        else:
            query_permissoes = "SELECT page_name FROM permissoes WHERE role = ?"
            df_permissoes = pd.read_sql_query(query_permissoes, conn, params=(perfil_selecionado,))
            paginas_atuais = df_permissoes['page_name'].tolist()
            
            with st.form(key=f"form_permissoes_{perfil_selecionado}"):
                st.write(f"Selecione as páginas que o perfil **{perfil_selecionado}** pode acessar:")
                paginas_selecionadas = st.multiselect("Páginas Acessíveis", options=PAGES, default=paginas_atuais, label_visibility="collapsed")
                
                if st.form_submit_button("Salvar Permissões"):
                    try:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM permissoes WHERE role = ?", (perfil_selecionado,))
                        if paginas_selecionadas:
                            dados_para_inserir = [(perfil_selecionado, page) for page in paginas_selecionadas]
                            cursor.executemany("INSERT INTO permissoes (role, page_name) VALUES (?, ?)", dados_para_inserir)
                        conn.commit()

                        # --- LINHA CORRIGIDA ---
                        # A mensagem de sucesso agora ficará visível e o cache será limpo.
                        # A linha st.rerun() foi removida.
                        st.success(f"Permissões para '{perfil_selecionado}' atualizadas com sucesso!")
                        st.cache_data.clear()

                    except Exception as e:
                        st.error(f"Erro ao salvar permissões: {e}")

with tab2:
    st.subheader("Criar um Novo Usuário")
    with st.form(key="form_criar_usuario", clear_on_submit=True):
        username = st.text_input("Usuário (login)").lower()
        name = st.text_input("Nome Completo")
        password = st.text_input("Senha", type="password")
        confirm_password = st.text_input("Confirmar Senha", type="password")
        role = st.selectbox("Perfil de Acesso", ROLES)
        if st.form_submit_button("Criar Usuário"):
            if not all([username, name, password, confirm_password, role]):
                st.warning("Todos os campos são obrigatórios.")
            elif password != confirm_password:
                st.error("As senhas não coincidem.")
            else:
                try:
                    password_bytes = password.encode('utf-8')
                    salt = bcrypt.gensalt()
                    hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO usuarios (username, name, password, role) VALUES (?, ?, ?, ?)", (username, name, hashed_password, role))
                    conn.commit()
                    st.success(f"Usuário '{username}' criado com sucesso!")
                except sqlite3.IntegrityError:
                    st.error(f"Erro: O usuário '{username}' já existe.")
                except Exception as e:
                    st.error(f"Erro ao criar usuário: {e}")
                    
with tab3:
    st.subheader("Usuários Cadastrados")
    df_usuarios = pd.read_sql_query("SELECT username, name, role FROM usuarios", conn)
    st.dataframe(df_usuarios, width='stretch', hide_index=True)
    st.markdown("---")
    st.subheader("Excluir um Usuário")
    usuarios_para_excluir = [u for u in df_usuarios['username'].tolist() if u.lower() != "master"]
    if not usuarios_para_excluir:
        st.write("Nenhum outro usuário para excluir.")
    else:
        usuario_selecionado = st.selectbox("Selecione o usuário para excluir", usuarios_para_excluir)
        if st.button("Excluir Usuário Selecionado", type="primary"):
            if usuario_selecionado:
                try:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM usuarios WHERE username = ?", (usuario_selecionado,))
                    conn.commit()
                    st.success(f"Usuário '{usuario_selecionado}' excluído!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir usuário: {e}")
conn.close()