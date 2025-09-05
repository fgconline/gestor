# pages/10_Controle_de_Acesso.py
import streamlit as st
import sqlite3
import pandas as pd
import bcrypt
import re
from pathlib import Path

# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(page_title="Controle de Acesso", layout="wide")
st.title("🔐 Painel de Controle de Acesso")

BASE_DIR = Path(__file__).parent.parent.resolve()  # sobe 1 nível (raiz do app)
PAGES_DIR = BASE_DIR / "pages"
PAGES_DIR.mkdir(exist_ok=True)

# -------------------------------
# Conexão e Helpers de BD
# -------------------------------
def criar_conexao():
    return sqlite3.connect(str(BASE_DIR / "gestor.db"))

def get_dataframe(query, params=()):
    conn = criar_conexao()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def run_query(query, params=()):
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()

def run_executemany(query, seq_params):
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.executemany(query, seq_params)
    conn.commit()
    conn.close()

# -------------------------------
# Garantias de esquema
# -------------------------------
def garantir_esquema():
    conn = criar_conexao()
    cur = conn.cursor()

    # Tabelas básicas (ajuste conforme seu schema real)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS perfis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            perfil_id INTEGER NOT NULL,
            FOREIGN KEY (perfil_id) REFERENCES perfis(id)
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paginas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_script TEXT NOT NULL UNIQUE,
            nome_amigavel TEXT NOT NULL,
            ordem INTEGER DEFAULT 0,
            icone TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permissoes (
            perfil_id INTEGER NOT NULL,
            pagina_id INTEGER NOT NULL,
            PRIMARY KEY (perfil_id, pagina_id),
            FOREIGN KEY (perfil_id) REFERENCES perfis(id),
            FOREIGN KEY (pagina_id) REFERENCES paginas(id)
        );
    """)

    # Índices úteis
    cur.execute("CREATE INDEX IF NOT EXISTS ix_paginas_ordem ON paginas (ordem ASC, id ASC);")

    # Garantir colunas 'ordem' e 'icone' se virem de base antiga
    cur.execute("PRAGMA table_info(paginas);")
    cols = [r[1] for r in cur.fetchall()]
    if 'ordem' not in cols:
        cur.execute("ALTER TABLE paginas ADD COLUMN ordem INTEGER DEFAULT 0;")
    if 'icone' not in cols:
        cur.execute("ALTER TABLE paginas ADD COLUMN icone TEXT;")

    # Seed mínimo (Admin)
    # Cria perfil Admin se não existir
    row = cur.execute("SELECT id FROM perfis WHERE nome='Admin';").fetchone()
    if not row:
        cur.execute("INSERT INTO perfis (nome) VALUES ('Admin');")

    conn.commit()
    conn.close()

def garantir_coluna_ordem_em_paginas():
    # Se recém criada, normaliza 0..n-1 pela ordem atual (ordem ASC, id ASC)
    conn = criar_conexao()
    cur = conn.cursor()
    cur.execute("SELECT id FROM paginas ORDER BY COALESCE(ordem,0) ASC, id ASC;")
    ids = [r[0] for r in cur.fetchall()]
    updates = [(idx, pid) for idx, pid in enumerate(ids)]
    cur.executemany("UPDATE paginas SET ordem=? WHERE id=?;", updates)
    conn.commit()
    conn.close()

garantir_esquema()
garantir_coluna_ordem_em_paginas()

# -------------------------------
# Permissão de acesso da página
# -------------------------------
if st.session_state.get("perfil") != 'Admin':
    st.error("Você não tem permissão para acessar esta página.")
    st.stop()

# -------------------------------
# Abas
# -------------------------------
tab1, tab2, tab3 = st.tabs(["Gerenciar Permissões", "Gerenciar Usuários", "Gerenciar Páginas"])

# ===============================
# TAB 1: PERMISSÕES
# ===============================
with tab1:
    st.header("Definir Acesso das Páginas por Perfil")

    perfis_df      = get_dataframe("SELECT id, nome FROM perfis")
    paginas_df     = get_dataframe("SELECT id, nome_script, nome_amigavel, COALESCE(ordem,0) AS ordem FROM paginas ORDER BY ordem ASC, id ASC")
    permissoes_df  = get_dataframe("SELECT perfil_id, pagina_id FROM permissoes")

    mapa_id_nome = paginas_df.set_index('id')['nome_amigavel'].to_dict()

    for _, perfil in perfis_df.iterrows():
        st.subheader(f"Perfil: {perfil['nome']}")

        paginas_permitidas_ids = permissoes_df[permissoes_df['perfil_id'] == perfil['id']]['pagina_id'].tolist()
        paginas_permitidas_nomes = [mapa_id_nome.get(pid) for pid in paginas_permitidas_ids if pid in mapa_id_nome]

        opcoes = st.multiselect(
            "Selecione as páginas que este perfil pode acessar:",
            options=paginas_df['nome_amigavel'].tolist(),
            default=paginas_permitidas_nomes,
            key=f"perm_{perfil['id']}"
        )

        if st.button(f"Salvar Permissões para {perfil['nome']}", key=f"btn_save_{perfil['id']}"):
            run_query("DELETE FROM permissoes WHERE perfil_id = ?", (perfil['id'],))
            ids_sel = paginas_df[paginas_df['nome_amigavel'].isin(opcoes)]['id'].tolist()
            for pid in ids_sel:
                run_query("INSERT INTO permissoes (perfil_id, pagina_id) VALUES (?, ?)", (perfil['id'], pid))
            st.success(f"Permissões para {perfil['nome']} atualizadas!")
            st.rerun()

# ===============================
# TAB 2: USUÁRIOS
# ===============================
with tab2:
    st.header("Criar e Gerenciar Usuários")

    perfis_df = get_dataframe("SELECT id, nome FROM perfis")

    # Criar usuário
    with st.form("novo_usuario_form", clear_on_submit=True):
        st.subheader("Criar Novo Usuário")
        email = st.text_input("Email do Usuário")
        senha = st.text_input("Senha", type="password")
        perfil_sel = st.selectbox("Perfil de Acesso", options=perfis_df['nome'].tolist())

        submit_button = st.form_submit_button("Criar Usuário")
        if submit_button:
            if email and senha and perfil_sel:
                try:
                    senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    perfil_id  = int(perfis_df[perfis_df['nome'] == perfil_sel]['id'].values[0])
                    run_query("INSERT INTO usuarios (email, senha_hash, perfil_id) VALUES (?, ?, ?)",
                              (email, senha_hash, perfil_id))
                    st.success(f"Usuário {email} criado com sucesso!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Erro: O email '{email}' já existe.")
                except Exception as e:
                    st.error(f"Ocorreu um erro: {e}")
            else:
                st.warning("Preencha todos os campos.")

    st.divider()

    # Alterar usuário
    st.subheader("Alterar Usuário")
    usuarios_df_alterar = get_dataframe("""
        SELECT u.id, u.email, u.perfil_id, p.nome as perfil_nome
        FROM usuarios u JOIN perfis p ON u.perfil_id = p.id
    """)
    lista_emails_alterar = usuarios_df_alterar['email'].tolist()

    if lista_emails_alterar:
        email_sel = st.selectbox("Selecione um usuário para alterar", options=lista_emails_alterar, index=None, placeholder="Selecione...")

        if email_sel:
            usuario_atual = usuarios_df_alterar[usuarios_df_alterar['email'] == email_sel].iloc[0]
            perfis_lista  = perfis_df['nome'].tolist()
            try:
                perfil_atual_index = perfis_lista.index(usuario_atual['perfil_nome'])
            except ValueError:
                perfil_atual_index = 0

            with st.form("alterar_usuario_form"):
                novo_perfil = st.selectbox("Novo Perfil", options=perfis_lista, index=perfil_atual_index)
                nova_senha  = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password")
                alterar_button = st.form_submit_button("Salvar Alterações")

                if alterar_button:
                    novo_perfil_id = int(perfis_df.loc[perfis_df['nome'] == novo_perfil, 'id'].iloc[0])
                    if nova_senha:
                        senha_hash = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        run_query("UPDATE usuarios SET perfil_id = ?, senha_hash = ? WHERE email = ?",
                                  (novo_perfil_id, senha_hash, email_sel))
                    else:
                        run_query("UPDATE usuarios SET perfil_id = ? WHERE email = ?",
                                  (novo_perfil_id, email_sel))
                    st.success(f"Usuário {email_sel} atualizado com sucesso!")
                    st.rerun()

    st.divider()

    # Excluir usuário
    st.subheader("Excluir Usuário")
    usuarios_df_excluir = get_dataframe("SELECT email FROM usuarios")
    lista_emails_excluir = usuarios_df_excluir['email'].tolist()

    if lista_emails_excluir:
        email_del = st.selectbox("Selecione um usuário para excluir", options=lista_emails_excluir, index=None, placeholder="Selecione...")

        if email_del:
            st.warning(f"Atenção: Esta ação é irreversível e excluirá o usuário **{email_del}** permanentemente.")
            confirmar = st.checkbox("Sim, eu confirmo que desejo excluir este usuário.")
            if st.button("Excluir Usuário"):
                if confirmar:
                    if email_del == st.session_state.get("email"):
                        st.error("Não é possível excluir o próprio usuário logado.")
                    else:
                        run_query("DELETE FROM usuarios WHERE email = ?", (email_del,))
                        st.success(f"Usuário {email_del} excluído com sucesso.")
                        st.rerun()
                else:
                    st.warning("Você precisa marcar a caixa de confirmação para excluir o usuário.")

    st.divider()
    st.subheader("Usuários Existentes")
    usuarios_com_perfil_df = get_dataframe("""
        SELECT u.id, u.email, p.nome as perfil
        FROM usuarios u LEFT JOIN perfis p ON u.perfil_id = p.id
    """)
    st.dataframe(usuarios_com_perfil_df, use_container_width=True, hide_index=True)

# ===============================
# TAB 3: PÁGINAS (ordem 0-based e criação de arquivo)
# ===============================
def nome_script_valido(nome: str) -> bool:
    return bool(re.match(r"^\d+_[A-Za-z0-9_-]+\.py$", nome or ""))

TEMPLATE_PAGINA = """import streamlit as st

st.set_page_config(page_title="{title}", layout="wide")
st.title("{icon} {title}")

st.info("Página criada automaticamente pelo Controle de Acesso. Edite este arquivo em pages/{filename}.")
"""

with tab3:
    st.header("Gerenciar Páginas (ordem inicia em 0)")
    st.caption("Esta ordem (0, 1, 2, …) será usada pelo **menu dinâmico**.")

    # Mostrar páginas e editar a ordem
    pgs = get_dataframe("SELECT id, nome_script, nome_amigavel, COALESCE(ordem,0) AS ordem, COALESCE(icone,'📄') AS icone FROM paginas ORDER BY ordem ASC, id ASC;")

    # Mostrar páginas com problemas (fantasmas/nome inválido)
    fantasmas = []
    for _, r in pgs.iterrows():
        if not nome_script_valido(r["nome_script"]):
            fantasmas.append((r["id"], r["nome_script"], "nome inválido (use NN_Nome.py)"))
        elif not (PAGES_DIR / r["nome_script"]).exists():
            fantasmas.append((r["id"], r["nome_script"], "arquivo ausente"))
    if fantasmas:
        st.warning("Páginas com problemas:")
        for pid, ns, motivo in fantasmas:
            st.write(f"- id={pid} | `{ns}` → {motivo}")

    if pgs.empty:
        st.info("Nenhuma página cadastrada. Use o formulário abaixo para criar.")
    else:
        with st.form("ordem_paginas_form"):
            st.subheader("Ordem das Páginas")
            novas_ordens = []
            for _, row in pgs.iterrows():
                col1, col2, col3, col4, col5 = st.columns([1, 3, 3, 2, 1])
                with col1:
                    st.write(f"ID: **{row['id']}**")
                with col2:
                    st.write(f"Script: `{row['nome_script']}`")
                with col3:
                    st.write(f"Nome: **{row['nome_amigavel']}**")
                with col4:
                    nova_ordem = st.number_input("ordem", min_value=0, max_value=10000, value=int(row['ordem']), step=1, key=f"ord_{row['id']}")
                    novas_ordens.append((int(nova_ordem), int(row['id'])))
                with col5:
                    st.write(row["icone"])

            salvar_ordem = st.form_submit_button("💾 Salvar Ordem (0-based)")
            if salvar_ordem:
                run_executemany("UPDATE paginas SET ordem=? WHERE id=?;", novas_ordens)
                st.success("Ordem das páginas atualizada!")
                st.rerun()

    st.divider()
    st.subheader("Adicionar Nova Página")

    with st.form("nova_pagina_form", clear_on_submit=True):
        nome_script   = st.text_input("Nome do script (ex: 11_Clientes.py)")
        nome_amigavel = st.text_input("Nome amigável (ex: Clientes)")
        icone         = st.text_input("Ícone (emoji opcional)", value="📄")
        ordem_inicial = st.number_input("Ordem inicial (0-based)", min_value=0, max_value=10000, value=0, step=1)
        criar_arquivo = st.checkbox("Criar arquivo automaticamente em /pages se não existir", value=True)

        cadastrar = st.form_submit_button("➕ Cadastrar Página")
        if cadastrar:
            if not nome_script_valido(nome_script):
                st.error("Nome inválido. Use o padrão:  NN_Nome.py  (ex.: 11_Clientes.py)")
            elif not nome_amigavel.strip():
                st.error("Informe o Nome amigável.")
            else:
                try:
                    destino = PAGES_DIR / nome_script
                    if criar_arquivo and not destino.exists():
                        destino.write_text(
                            TEMPLATE_PAGINA.format(
                                title=nome_amigavel.strip(),
                                icon=icone.strip() or "📄",
                                filename=nome_script,
                            ),
                            encoding="utf-8"
                        )
                        st.success(f"Arquivo criado: pages/{nome_script}")

                    run_query(
                        "INSERT INTO paginas (nome_script, nome_amigavel, ordem, icone) VALUES (?, ?, ?, ?);",
                        (nome_script.strip(), nome_amigavel.strip(), int(ordem_inicial), icone.strip() or "📄")
                    )
                    st.success("Página cadastrada com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar página: {e}")

    st.divider()
    st.subheader("Excluir Página")
    paginas_df2 = get_dataframe("SELECT id, nome_amigavel FROM paginas ORDER BY ordem ASC, id ASC;")
    if not paginas_df2.empty:
        map_id_nome = {f"[{r['id']}] {r['nome_amigavel']}": int(r['id']) for _, r in paginas_df2.iterrows()}
        sel = st.selectbox("Selecione a página para excluir", options=[""] + list(map_id_nome.keys()))
        if sel:
            st.warning("A exclusão removerá também as permissões associadas a ela.")
            confirmar = st.checkbox("Sim, desejo excluir esta página e suas permissões.")
            if st.button("🗑️ Excluir Página"):
                if confirmar:
                    pid = map_id_nome[sel]
                    run_query("DELETE FROM permissoes WHERE pagina_id = ?;", (pid,))
                    run_query("DELETE FROM paginas WHERE id = ?;", (pid,))
                    st.success("Página excluída com sucesso.")
                    st.rerun()
                else:
                    st.info("Marque a confirmação para excluir.")
