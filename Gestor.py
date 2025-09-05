# Gestor.py
# ============================================
# App shell com LOGIN + navegação dinâmica
# - Checa login real (session_state.logged_in / email / perfil)
# - Sem pandas (evita RecursionError)
# - Sem fallback recursivo (não roda o próprio Gestor como página)
# - Garante esquema de 'usuarios', 'perfis', 'paginas', 'permissoes'
# ============================================
import streamlit as st
import sqlite3
import re
from pathlib import Path

# ------------ CONFIG BÁSICA ------------
st.set_page_config(page_title="Gestor", page_icon="📊", layout="wide")

BASE_DIR = Path(__file__).parent.resolve()
PAGES_DIR = BASE_DIR / "pages"
DB_PATH = str(BASE_DIR / "gestor.db")  # ponto-verdade do banco

# ------------ DEPENDÊNCIA OPCIONAL: bcrypt ------------
try:
    import bcrypt
    HAS_BCRYPT = True
except Exception:
    HAS_BCRYPT = False

# ------------ CONEXÃO E ESQUEMA ------------
def conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA foreign_keys = ON;")
    return c

def garantir_esquema():
    con = conn()
    cur = con.cursor()

    # PERFIS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS perfis (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        );
    """)

    # USUÁRIOS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            perfil_id  INTEGER NOT NULL,
            FOREIGN KEY (perfil_id) REFERENCES perfis(id)
        );
    """)

    # PÁGINAS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paginas (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_script   TEXT NOT NULL UNIQUE,
            nome_amigavel TEXT NOT NULL,
            ordem         INTEGER DEFAULT 0,
            icone         TEXT
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_paginas_ordem ON paginas (ordem ASC, id ASC);")
    # garantir colunas (bases antigas)
    cur.execute("PRAGMA table_info(paginas);")
    cols = [r[1] for r in cur.fetchall()]
    if "icone" not in cols:
        cur.execute("ALTER TABLE paginas ADD COLUMN icone TEXT;")
    if "ordem" not in cols:
        cur.execute("ALTER TABLE paginas ADD COLUMN ordem INTEGER DEFAULT 0;")
        ids = [r[0] for r in cur.execute("SELECT id FROM paginas ORDER BY id;").fetchall()]
        cur.executemany("UPDATE paginas SET ordem=? WHERE id=?;", [(i, pid) for i, pid in enumerate(ids)])

    # PERMISSÕES
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permissoes (
            perfil_id INTEGER NOT NULL,
            pagina_id INTEGER NOT NULL,
            PRIMARY KEY (perfil_id, pagina_id),
            FOREIGN KEY (perfil_id) REFERENCES perfis(id),
            FOREIGN KEY (pagina_id) REFERENCES paginas(id)
        );
    """)

    # SEED mínimo: perfil Admin + usuário admin se não houver nenhum usuário
    row = cur.execute("SELECT COUNT(*) FROM usuarios;").fetchone()
    usuarios_count = row[0] if row else 0
    if usuarios_count == 0:
        # perfil admin
        rowp = cur.execute("SELECT id FROM perfis WHERE nome='Admin';").fetchone()
        if rowp:
            admin_pid = rowp[0]
        else:
            cur.execute("INSERT INTO perfis (nome) VALUES ('Admin');")
            admin_pid = cur.lastrowid

        # senha padrão "admin" (para desenvolvimento)
        if HAS_BCRYPT:
            senha_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode("utf-8")
        else:
            # fallback fraco (recomendado instalar bcrypt): string fixa
            senha_hash = "sha$admin"

        cur.execute(
            "INSERT INTO usuarios (email, senha_hash, perfil_id) VALUES (?, ?, ?);",
            ("admin@local", senha_hash, admin_pid)
        )

    con.commit()
    con.close()

garantir_esquema()

# ------------ AUTH ------------
def autenticar(email: str, senha: str):
    """
    Retorna (ok: bool, perfil_nome: str|None, msg: str|None)
    """
    con = conn()
    cur = con.cursor()
    user = cur.execute("""
        SELECT u.senha_hash, p.nome
        FROM usuarios u
        JOIN perfis p ON p.id = u.perfil_id
        WHERE u.email = ?;
    """, (email,)).fetchone()
    con.close()

    if not user:
        return False, None, "Usuário não encontrado."

    senha_hash, perfil_nome = user
    if HAS_BCRYPT and senha_hash and senha_hash.startswith("$2"):
        ok = bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))
    else:
        # fallback fraco: aceita se senha == "admin" e hash é "sha$admin"
        ok = (senha == "admin" and senha_hash == "sha$admin")

    if not ok:
        return False, None, "Senha inválida."
    return True, perfil_nome, None

# ------------ LOGIN UI ------------
def tela_login():
    st.title("🔐 Login")
    if not HAS_BCRYPT:
        st.warning("Pacote **bcrypt** não encontrado. Para segurança, instale com: `pip install bcrypt`.\n"
                   "Por ora, apenas o usuário seed `admin@local` com senha `admin` funcionará (fallback fraco).")

    with st.form("login_form"):
        email = st.text_input("E-mail", value="")
        senha = st.text_input("Senha", value="", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True)

    if entrar:
        if not email or not senha:
            st.error("Informe e-mail e senha.")
            st.stop()
        ok, perfil_nome, msg = autenticar(email.strip(), senha.strip())
        if ok:
            st.session_state.logged_in = True
            st.session_state.email = email.strip()
            st.session_state.perfil = perfil_nome or ""
            st.success("Login realizado com sucesso!")
            st.rerun()
        else:
            st.error(msg or "Falha na autenticação.")

# ------------ NAV: montar páginas autorizadas ------------
def nav_pages_from_db(email: str):
    """
    Lê as páginas permitidas para o usuário (via perfil/permissões) e cria objetos st.Page
    apenas para arquivos que existem em /pages.
    Sem pandas: sqlite3 + tuplas.
    """
    rows = []
    try:
        con = conn()
        cur = con.cursor()
        # Páginas autorizadas ao perfil do usuário
        cur.execute("""
            SELECT p.nome_script,
                   p.nome_amigavel,
                   COALESCE(p.icone, '📄') AS icone
            FROM paginas p
            JOIN permissoes perm ON perm.pagina_id = p.id
            JOIN usuarios u ON u.perfil_id = perm.perfil_id
            WHERE u.email = ?
            ORDER BY COALESCE(p.ordem,0) ASC, p.id ASC;
        """, (email,))
        rows = cur.fetchall()  # [(nome_script, nome_amigavel, icone), ...]
    except Exception as e:
        st.error(f"Erro lendo páginas do banco: {e}")
    finally:
        try:
            con.close()
        except Exception:
            pass

    pages = []
    for (nome_script, nome_amigavel, icone) in rows:
        script_name = (nome_script or "").strip()
        nome_label  = (nome_amigavel or script_name or "Página")
        icon        = (icone or "📄")

        # Sanidade: "NN_Nome.py"
        if not re.match(r"^\d+_[A-Za-z0-9_-]+\.py$", script_name):
            st.warning(f"Nome de página inválido no banco: {script_name}")
            continue

        full_path = PAGES_DIR / script_name
        if full_path.exists():
            pages.append(st.Page(str(full_path), title=nome_label, icon=icon))
        else:
            st.warning(f"Arquivo não encontrado: pages/{script_name}. Ajuste no Controle de Acesso.")

    return pages

# ============ FLUXO ============
# 1) Sem login? mostra tela de login e para.
if not st.session_state.get("logged_in", False):
    tela_login()
    st.stop()

# 2) Com login, precisa ter e-mail
usuario_email = st.session_state.get("email", "")
if not usuario_email:
    st.error("Sessão sem e-mail. Faça login novamente.")
    # Limpa e volta pro login
    st.session_state.clear()
    st.rerun()

# 3) Navbar + Logout
col1, col2 = st.columns([6,1])
with col1:
    st.caption(f"Usuário: {usuario_email}  |  Perfil: {st.session_state.get('perfil','')}")
with col2:
    if st.button("Sair", use_container_width=True):
        st.session_state.clear()
        st.success("Sessão encerrada.")
        st.rerun()

# 4) Monta navegação pelas permissões do usuário
pages = nav_pages_from_db(usuario_email)

if not pages:
    st.title("🏠 Home")
    st.info("Nenhuma página autorizada para este usuário ou arquivos não encontrados em `/pages`.")
    st.caption("Use **Controle de Acesso** para cadastrar páginas e permissões, e garanta os arquivos em `pages/`.")
    st.stop()

# 5) Cria o navigation normalmente
nav = st.navigation({"Menu": pages})
nav.run()
