# --------------------------------------------
# pages/11_Clientes.py | Clientes (Segmento travado + UPSERT + Exclusão robusta)
# --------------------------------------------
import streamlit as st
import sqlite3
import pandas as pd
import os
import unicodedata
from typing import Optional
from pathlib import Path

# ========== CONFIG ==========
st.set_page_config(page_title="Clientes | Gestor", layout="wide")
st.title("👥 Clientes")

# ========== DB PATH (secrets -> env -> <raiz>/gestor.db) ==========
BASE_DIR = Path(__file__).parent.parent.resolve()  # raiz do app
DEFAULT_DB_PATH = str(BASE_DIR / "gestor.db")
try:
    DB_PATH = st.secrets["DB_PATH"]
except Exception:
    DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)

# ========== Tabela de Segmentos (Código ↔ Nome) ==========
SEGMENTOS_LIST = [
    ("007", "AUTOMOTIVO"),
    ("006", "BUREAU"),
    ("001", "COMUNICACAO VISUAL"),
    ("004", "CONSUMIDOR FINAL"),
    ("010", "DECORACAO"),
    ("002", "DISTRIBUIDORAS/REVEDAS"),
    ("100", "DIVERSOS"),
    ("005", "GRAFICA"),
    ("003", "INDUSTRIAS"),
    ("016", "REFERENCIA HUB 1"),
    ("017", "REFERENCIA HUB 2"),
    ("018", "REFERENCIA HUB 3"),
    ("019", "REFERENCIA HUB 4"),
    ("012", "REVENDA HUB 1"),
    ("013", "REVENDA HUB 2"),
    ("014", "REVENDA HUB 3"),
    ("015", "REVENDA HUB 4"),
    ("008", "SINALIZACAO"),
    ("009", "TEXTIL"),
    ("011", "TRANSPORTADORA"),
]
SEGMENTO_COD2NOME = {c: n for c, n in SEGMENTOS_LIST}
SEGMENTO_NOME2COD = {n: c for c, n in SEGMENTOS_LIST}
SEGMENTOS_LABELS = [f"{c} — {n}" for c, n in SEGMENTOS_LIST]

def int_to_code3(x: Optional[int]) -> Optional[str]:
    if x is None:
        return None
    try:
        return f"{int(x):03d}"
    except Exception:
        return None

# ========== Helpers ==========
def conn():
    c = sqlite3.connect(DB_PATH)
    # Ativa FK sempre
    c.execute("PRAGMA foreign_keys = ON;")
    return c

def sem_acentos(s: str) -> str:
    if s is None:
        return s
    return ''.join(c for c in unicodedata.normalize('NFD', str(s))
                   if unicodedata.category(c) != 'Mn')

def garantir_tabela_clientes():
    ddl = """
    CREATE TABLE IF NOT EXISTS clientes (
        CodCli   INTEGER PRIMARY KEY,
        Nome     TEXT NOT NULL,
        Email    TEXT,
        Estado   TEXT,
        Cidade   TEXT,
        Fone     TEXT,
        CodSeg   INTEGER,
        NomeSeg  TEXT,
        CodTag   TEXT
    );
    """
    idx = [
        "CREATE INDEX IF NOT EXISTS ix_clientes_nome   ON clientes (Nome);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_email  ON clientes (Email);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_estado ON clientes (Estado);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_cidade ON clientes (Cidade);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_codseg ON clientes (CodSeg);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_codtag ON clientes (CodTag);",
    ]
    with conn() as c:
        c.execute(ddl)
        for sql in idx:
            c.execute(sql)
        c.commit()

def pesquisar_clientes_multitermo(q: str, limite: int = 300) -> pd.DataFrame:
    termos = [t.strip() for t in q.split() if t.strip()]
    if not termos:
        return pd.DataFrame(columns=["CodCli","Nome","Estado","Cidade","Email","Fone","CodSeg","NomeSeg","CodTag"])

    wheres, args = [], []
    termos_txt = [t for t in termos if not t.isdigit()]
    termos_cod = [t for t in termos if t.isdigit()]

    for t in termos_txt:
        wheres.append("UPPER(Nome) LIKE UPPER(?)")
        args.append(f"%{t}%")

    if termos_cod:
        bloco = " OR ".join(["CAST(CodCli AS TEXT) LIKE ?"] * len(termos_cod))
        wheres.append(f"({bloco})")
        args.extend([f"%{t}%" for t in termos_cod])

    where_sql = " AND ".join(wheres) if wheres else "1=1"

    with conn() as c:
        cur = c.execute(f"""
            SELECT CodCli, Nome, Estado, Cidade, Email, Fone, CodSeg, NomeSeg, CodTag
            FROM clientes
            WHERE {where_sql}
            ORDER BY Nome ASC
            LIMIT ?;
        """, (*args, limite))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=cols)

def buscar_por_codcli(codcli: int):
    with conn() as c:
        return c.execute("""
            SELECT CodCli, Nome, Email, Estado, Cidade, Fone, CodSeg, NomeSeg, CodTag
            FROM clientes WHERE CodCli=?;
        """, (codcli,)).fetchone()

def atualizar_cliente(payload: dict):
    with conn() as c:
        c.execute("""
            UPDATE clientes SET
                Nome=?, Email=?, Estado=?, Cidade=?, Fone=?,
                CodSeg=?, NomeSeg=?, CodTag=?
            WHERE CodCli=?;
        """, (
            payload["Nome"], payload["Email"], payload["Estado"], payload["Cidade"],
            payload["Fone"], payload["CodSeg"], payload["NomeSeg"], payload["CodTag"],
            payload["CodCli"],
        ))
        c.commit()

# --------- UPSERT (cria/atualiza) ----------
def inserir_cliente(payload: dict):
    with conn() as c:
        c.execute("""
            INSERT INTO clientes (CodCli, Nome, Email, Estado, Cidade, Fone, CodSeg, NomeSeg, CodTag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(CodCli) DO UPDATE SET
                Nome   = excluded.Nome,
                Email  = excluded.Email,
                Estado = excluded.Estado,
                Cidade = excluded.Cidade,
                Fone   = excluded.Fone,
                CodSeg = excluded.CodSeg,
                NomeSeg= excluded.NomeSeg,
                CodTag = excluded.CodTag;
        """, (
            payload.get("CodCli"), payload.get("Nome"), payload.get("Email"),
            payload.get("Estado"), payload.get("Cidade"), payload.get("Fone"),
            payload.get("CodSeg"), payload.get("NomeSeg"), payload.get("CodTag"),
        ))
        c.commit()

# --------- Exclusão segura ----------
def excluir_cliente(codcli: int, cascade: bool = False) -> int:
    """
    Exclui cliente. Se cascade=True, remove vínculos em vendas/pedidos antes.
    Retorna quantidade de linhas removidas da tabela clientes (0 ou 1).
    """
    with conn() as c:
        cur = c.cursor()
        try:
            if cascade:
                # ajuste se seus nomes de colunas diferirem
                cur.execute("DELETE FROM vendas  WHERE CodCli = ?;", (codcli,))
                cur.execute("DELETE FROM pedidos WHERE codcli = ?;", (codcli,))
            cur.execute("DELETE FROM clientes WHERE CodCli = ?;", (codcli,))
            c.commit()
            return cur.rowcount  # 0 ou 1 para a tabela clientes
        except sqlite3.IntegrityError as e:
            # Mensagem clara quando travar por FK
            raise RuntimeError("Falha de integridade referencial (FK). Há registros dependentes em outras tabelas.") from e

# ---------- util: Segmento coerente ----------
def segmento_resolver(codseg: Optional[int], nomeseg: Optional[str]) -> str:
    code3 = int_to_code3(codseg) if codseg is not None else None
    if code3 and code3 in SEGMENTO_COD2NOME:
        return code3
    if nomeseg and nomeseg in SEGMENTO_NOME2COD:
        return SEGMENTO_NOME2COD[nomeseg]
    return SEGMENTOS_LIST[0][0]

# ========== Gate opcional ==========
if not st.session_state.get("logged_in", True):
    st.error("Faça o login para acessar esta página.")
    st.stop()

# ========== Garantir estrutura ==========
garantir_tabela_clientes()

# ======================================================================
#                        BUSCAR & LISTAR (ENXUTO)
# ======================================================================
with st.container():
    col1, col2 = st.columns([4,1])
    with col1:
        q = st.text_input("🔎 Buscar por código e/ou nome (separe termos por espaço)", placeholder="ex.: 1234 joao sp")
    with col2:
        st.write("")  # espaçador
        st.button("Procurar", type="primary", key="btn_buscar")  # opcional, só visual

result = pesquisar_clientes_multitermo(q) if q.strip() else pd.DataFrame(columns=["CodCli","Nome","Estado","Cidade","Email","Fone","CodSeg","NomeSeg","CodTag"])

if not result.empty:
    st.dataframe(result[["CodCli","Nome","Estado","Cidade"]], use_container_width=True, hide_index=True, height=240)
else:
    st.info("Digite acima para pesquisar. Mostro aqui os resultados.")

# Seleção do cliente encontrado
opcoes_map = {}
if not result.empty:
    for _, r in result.iterrows():
        label = f"{int(r['CodCli'])} — {r['Nome']} ({(r['Estado'] or '')}/{(r['Cidade'] or '')})"
        opcoes_map[label] = int(r["CodCli"])

sel_label = st.selectbox(
    "Selecione um cliente dos resultados",
    options=[""] + list(opcoes_map.keys()),
    index=0,
    placeholder="Selecione…",
    key="sel_cliente_edicao"
)

col_load1, col_load2 = st.columns([1,9])
with col_load1:
    carregar = st.button("⬇️ Carregar", key="btn_carregar")
with col_load2:
    st.write("")

# Estado do formulário (sempre inicia vazio)
if "edit_payload" not in st.session_state:
    st.session_state.edit_payload = {
        "CodCli": "", "Nome": "", "Email": "", "Estado": "", "Cidade": "",
        "Fone": "", "CodSeg": 0, "NomeSeg": "", "CodTag": ""
    }

if carregar and sel_label and sel_label in opcoes_map:
    r = buscar_por_codcli(opcoes_map[sel_label])
    if r:
        CodCli, Nome, Email, Estado, Cidade, Fone, CodSeg, NomeSeg, CodTag = r
        code3 = segmento_resolver(CodSeg, NomeSeg)
        nome_oficial = SEGMENTO_COD2NOME[code3]
        if (int_to_code3(CodSeg) != code3) or ((NomeSeg or "") != nome_oficial):
            st.warning("Segmento deste cliente estava inconsistente e será normalizado ao salvar.")
        st.session_state.edit_payload = {
            "CodCli": CodCli,
            "Nome": Nome or "",
            "Email": Email or "",
            "Estado": (Estado or "")[:2].upper(),
            "Cidade": Cidade or "",
            "Fone": Fone or "",
            "CodSeg": int(code3),
            "NomeSeg": nome_oficial,
            "CodTag": CodTag or "",
        }
        st.success(f"Cliente {CodCli} carregado.")

st.divider()

# ======================================================================
#                         FORMULÁRIO (ALTERAR / EXCLUIR)
# ======================================================================
st.subheader("✏️ Alterar / 🗑️ Excluir")

with st.form("form_edit"):
    col1, col2, col3 = st.columns([1,2,2])
    with col1:
        st.text_input("CodCli", value=str(st.session_state.edit_payload["CodCli"]), disabled=True, key="fld_codcli")
    with col2:
        nome_val = st.text_input("Nome", value=st.session_state.edit_payload["Nome"], key="fld_nome")
    with col3:
        email_val = st.text_input("Email", value=st.session_state.edit_payload["Email"], key="fld_email")

    col4, col5, col6 = st.columns([1,2,2])
    with col4:
        estado_val = st.text_input("Estado (UF)", value=st.session_state.edit_payload["Estado"], key="fld_estado").upper()[:2]
    with col5:
        cidade_val = st.text_input("Cidade", value=st.session_state.edit_payload["Cidade"], key="fld_cidade")
    with col6:
        fone_val = st.text_input("Fone", value=st.session_state.edit_payload["Fone"], key="fld_fone")

    # -------- SEGMENTO TRAVADO --------
    st.markdown("**Segmento (travado CodSeg ↔ NomeSeg)**")
    if st.session_state.edit_payload["CodSeg"]:
        code_default = int_to_code3(st.session_state.edit_payload["CodSeg"])
    else:
        code_default = SEGMENTOS_LIST[0][0]
    default_label = f"{code_default} — {SEGMENTO_COD2NOME[code_default]}"
    try:
        default_index = SEGMENTOS_LABELS.index(default_label)
    except ValueError:
        default_index = 0

    segmento_label = st.selectbox(
        "Segmento",
        options=SEGMENTOS_LABELS,
        index=default_index,
        key="fld_segmento_label"
    )
    sel_code = segmento_label.split(" — ", 1)[0]
    sel_name = SEGMENTO_COD2NOME[sel_code]

    col9a, col9b, col9c = st.columns([1,1,6])
    with col9a:
        salvar = st.form_submit_button("💾 Salvar", use_container_width=True)
    with col9b:
        excluir = st.form_submit_button("🗑️ Excluir", use_container_width=True)

# Ações do formulário
if salvar:
    if not str(st.session_state.edit_payload["CodCli"]).strip():
        st.error("Nenhum cliente carregado. Pesquise, selecione e clique **Carregar**.")
    else:
        payload = {
            "CodCli": int(st.session_state.edit_payload["CodCli"]),
            "Nome": nome_val.strip(),
            "Email": email_val.strip(),
            "Estado": estado_val.strip()[:2].upper(),
            "Cidade": cidade_val.strip(),
            "Fone": fone_val.strip(),
            "CodSeg": int(sel_code),   # TRAVADO
            "NomeSeg": sel_name,       # TRAVADO
            "CodTag": st.session_state.edit_payload["CodTag"],
        }
        try:
            atualizar_cliente(payload)
            st.success("Cliente atualizado com sucesso!")
            st.session_state.edit_payload.update(payload)
        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")

if excluir:
    if not str(st.session_state.edit_payload["CodCli"]).strip():
        st.error("Nenhum cliente carregado.")
    else:
        cod = int(st.session_state.edit_payload["CodCli"])
        st.warning(f"Confirma excluir o cliente **{cod}**? Esta ação é irreversível.")
        cascade = st.checkbox("Excluir também vínculos (vendas/pedidos) se existirem", key=f"chk_cascade_{cod}")
        confirmar = st.checkbox("Sim, desejo excluir este cliente.", key=f"chk_confirm_excluir_{cod}")
        if st.button("Excluir definitivamente", key=f"btn_excluir_def_{cod}"):
            if not confirmar:
                st.info("Marque a confirmação para prosseguir.")
            else:
                try:
                    deleted = excluir_cliente(cod, cascade=cascade)
                    if deleted == 1:
                        st.success("Cliente excluído.")
                    else:
                        st.warning("Nada foi excluído (cliente já não existia).")
                    # limpa o formulário
                    st.session_state.edit_payload = {
                        "CodCli": "", "Nome": "", "Email": "", "Estado": "", "Cidade": "",
                        "Fone": "", "CodSeg": 0, "NomeSeg": "", "CodTag": ""
                    }
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))
                    st.info("Ative a opção **'Excluir também vínculos (vendas/pedidos)'** para forçar a remoção, ou remova as referências manualmente.")
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")

st.divider()

# ======================================================================
#                        INSERIR (NOVO CLIENTE) — UPSERT
# ======================================================================
with st.expander("➕ Cadastrar novo cliente", expanded=False):
    with st.form("form_new"):
        col1, col2, col3 = st.columns([1,2,2])
        with col1:
            CodCli_new = st.number_input("CodCli (obrigatório)", value=0, step=1, key="new_codcli")
        with col2:
            Nome_new = st.text_input("Nome*", value="", key="new_nome")
        with col3:
            Email_new = st.text_input("Email", value="", key="new_email")

        col4, col5, col6 = st.columns([1,1,2])
        with col4:
            Estado_new = st.text_input("Estado (UF)", value="", key="new_estado").upper()[:2]
        with col5:
            Cidade_new = st.text_input("Cidade", value="", key="new_cidade")
        with col6:
            Fone_new = st.text_input("Fone", value="", key="new_fone")

        st.markdown("**Segmento (travado CodSeg ↔ NomeSeg)**")
        segmento_label_new = st.selectbox(
            "Segmento",
            options=SEGMENTOS_LABELS,
            index=0,
            key="new_segmento_label"
        )
        sel_code_new = segmento_label_new.split(" — ", 1)[0]
        sel_name_new = SEGMENTO_COD2NOME[sel_code_new]

        colb1, _ = st.columns([1,9])
        with colb1:
            criar = st.form_submit_button("✅ Criar/Atualizar (Upsert)", use_container_width=True)

    if criar:
        if CodCli_new <= 0 or not Nome_new.strip():
            st.error("Informe **CodCli (>0)** e **Nome**.")
        else:
            pay = {
                "CodCli": int(CodCli_new),
                "Nome": Nome_new.strip(),
                "Email": Email_new.strip(),
                "Estado": Estado_new.strip()[:2].upper(),
                "Cidade": Cidade_new.strip(),
                "Fone": Fone_new.strip(),
                "CodSeg": int(sel_code_new),  # TRAVADO
                "NomeSeg": sel_name_new,      # TRAVADO
                "CodTag": "",
            }
            try:
                inserir_cliente(pay)  # UPSERT
                st.success("Cliente criado/atualizado com sucesso!")
                st.session_state.edit_payload = {**pay}
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao criar/atualizar: {e}")
