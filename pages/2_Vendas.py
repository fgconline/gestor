import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# -----------------------
# Gate de acesso
# -----------------------
if not st.session_state.get("logged_in", False):
    st.error("Por favor, faça o login para acessar esta página.")
    st.stop()

st.title("📈 Vendas")

# -----------------------
# Utilitários
# -----------------------
def criar_conexao():
    return sqlite3.connect("gestor.db")

@st.cache_data(show_spinner=True)
def carregar_vendas():
    """Carrega vendas e (opcional) produtos.m2 + vendedor, com fallback seguro."""
    conn = criar_conexao()
    vendedor_presente = False
    try:
        q = """
            SELECT 
                v.Data_NF,
                v.Nome_do_Cliente,
                v.Descricao_do_Produto,
                v.UF,
                v.Valor_Total,
                v.QtdeFaturada,
                v.Codpro,
                v.Codcli,
                v.Nome_do_Vendedor AS Nome_Vendedor,
                v.Empresa,
                p.m2
            FROM vendas v
            LEFT JOIN produtos p ON v.Codpro = p.CodPro
        """
        df = pd.read_sql_query(q, conn)
        vendedor_presente = "Nome_Vendedor" in df.columns
    except Exception:
        q = """
            SELECT 
                v.Data_NF,
                v.Nome_do_Cliente,
                v.Descricao_do_Produto,
                v.UF,
                v.Valor_Total,
                v.QtdeFaturada,
                v.Codpro,
                v.Codcli
            FROM vendas v
        """
        df = pd.read_sql_query(q, conn)
        df["Nome_Vendedor"] = None
        df["m2"] = None
        df["Empresa"] = None
        vendedor_presente = False
    finally:
        conn.close()

    # Tipagem e campos auxiliares
    df["Data_NF"] = pd.to_datetime(df["Data_NF"], errors="coerce")
    df = df.dropna(subset=["Data_NF"])
    df["Ano"] = df["Data_NF"].dt.year
    df["Mes"] = df["Data_NF"].dt.month
    df["Dia"] = df["Data_NF"].dt.day

    for col in ["Valor_Total", "QtdeFaturada", "m2"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "m2" not in df.columns:
        df["m2"] = 1
    df["m2"] = df["m2"].fillna(1)
    df.loc[df["m2"] <= 0, "m2"] = 1

    if "QtdeFaturada" not in df.columns:
        df["QtdeFaturada"] = 0

    df["Rolos"] = df["QtdeFaturada"] / df["m2"]

    # Normalizações de texto
    for col in ["UF", "Nome_do_Cliente", "Descricao_do_Produto", "Nome_Vendedor", "Codpro", "Codcli"]:
        if col in df.columns:
            df[col] = df[col].astype(str).fillna("")

    # Empresa numérica quando possível
    if "Empresa" in df.columns:
        df["Empresa"] = pd.to_numeric(df["Empresa"], errors="coerce")

    return df, vendedor_presente

def fmt(x):
    try:
        return f"{x:,.0f}".replace(",", ".")
    except Exception:
        return x

NOME_MESES = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

def aplicar_pesquisa(df_in, termos_raw):
    """Filtra df_in por múltiplos termos em campos principais."""
    if not termos_raw or not termos_raw.strip():
        return df_in
    termos = [t.strip() for t in termos_raw.split(",") if t.strip()]
    campos = ["Codpro", "Codcli", "Nome_do_Cliente", "Descricao_do_Produto", "UF"]
    mask_final = pd.Series(True, index=df_in.index)
    for termo in termos:
        m = pd.Series(False, index=df_in.index)
        for col in campos:
            if col in df_in.columns:
                m |= df_in[col].astype(str).str.contains(termo, case=False, na=False)
        mask_final &= m
    return df_in.loc[mask_final]

# -----------------------
# Carregar dados
# -----------------------
try:
    df, vendedor_disponivel = carregar_vendas()
except Exception as e:
    st.error("Falha ao carregar dados de vendas.")
    st.exception(e)
    st.stop()

if df.empty:
    st.info("Nenhuma venda encontrada no banco (tabela 'vendas' vazia).")
    st.stop()

# -----------------------
# Sidebar de filtros + pesquisa múltipla
# (1) Filtros de tempo/UF/Empresa
# (2) Pesquisa múltipla
# (3) Vendedores DINÂMICOS conforme (1)+(2)
# -----------------------
st.sidebar.header("Filtros")

anos  = sorted(df["Ano"].unique().tolist())
meses = sorted(df["Mes"].unique().tolist())
ufs   = sorted(df["UF"].unique().tolist())
ano_atual   = datetime.now().year
default_ano = [ano_atual] if ano_atual in anos else anos

# Botão limpar
if st.sidebar.button("Limpar filtros", type="secondary"):
    for k in ("anos_sel","meses_sel","ufs_sel","vendedores_sel",
              "empresas_sel","pesquisa_termos","unidade_qty",
              "agrupamento_key","metrica_key","visao_key"):
        st.session_state.pop(k, None)
    st.rerun()

anos_sel = st.sidebar.multiselect("Ano(s)", anos, default=default_ano, key="anos_sel")
meses_sel = st.sidebar.multiselect(
    "Mês(es)", meses, default=meses, format_func=lambda x: NOME_MESES.get(x, x), key="meses_sel"
)
ufs_sel = st.sidebar.multiselect("UF(s)", ufs, default=ufs, key="ufs_sel")

# Empresa (3=Loja, 1=Distribuidora)
if "Empresa" in df.columns:
    mapa_empresa = {1: "Distribuidora", 3: "Loja"}
    df["Empresa_Label"] = df["Empresa"].map(mapa_empresa).fillna(
        df["Empresa"].apply(lambda x: "" if pd.isna(x) else str(int(x)) if float(x).is_integer() else str(x))
    )
    empresas_opts = sorted([opt for opt in df["Empresa_Label"].unique().tolist() if opt != ""])
    empresas_sel = st.sidebar.multiselect(
        "Empresa(s)", empresas_opts, default=empresas_opts, key="empresas_sel"
    )
else:
    empresas_sel = []

# (1) FILTRO BASE (sem vendedor ainda)
filtro_base = (df["Ano"].isin(anos_sel)) & (df["Mes"].isin(meses_sel)) & (df["UF"].isin(ufs_sel))
if "Empresa_Label" in df.columns and empresas_sel:
    filtro_base &= df["Empresa_Label"].isin(empresas_sel)
df_base = df.loc[filtro_base].copy()

# (2) PESQUISA MÚLTIPLA antes do filtro de vendedor
termos_raw = st.text_input(
    "Pesquisar por múltiplos termos (separe por vírgula)",
    placeholder="Ex: 507, cliente, SP",
    key="pesquisa_termos"
)
df_pos_pesquisa = aplicar_pesquisa(df_base, termos_raw)

if df_pos_pesquisa.empty:
    st.warning("Sem resultados para os filtros/pesquisa atuais.")
    st.stop()

# (3) VENDEDORES DINÂMICOS com base no df_pos_pesquisa
if "Nome_Vendedor" in df_pos_pesquisa.columns:
    vendedores_opts = sorted(df_pos_pesquisa["Nome_Vendedor"].dropna().unique().tolist())
    vendedores_sel = st.sidebar.multiselect(
        "Vendedor(es) (apenas os que aparecem no resultado atual)",
        vendedores_opts, default=vendedores_opts, key="vendedores_sel"
    )
else:
    vendedores_sel = []

# Agora aplica o filtro de vendedores sobre o df_pos_pesquisa
if vendedores_sel:
    df_view = df_pos_pesquisa[df_pos_pesquisa["Nome_Vendedor"].isin(vendedores_sel)].copy()
else:
    df_view = df_pos_pesquisa.copy()

if df_view.empty:
    st.warning("Sem resultados após aplicar o filtro de vendedor.")
    st.stop()

# -----------------------
# Controles de visualização
# -----------------------
st.write("---")
c1, c2, c3, c4 = st.columns([1,1,1,1.2])

with c1:
    agrupamento = st.radio("Agrupar por:", ("Cliente", "Produto", "UF"),
                           horizontal=True, key="agrupamento_key")
with c2:
    metrica = st.radio("Métrica:", ("Valor", "Quantidade"),
                       horizontal=True, key="metrica_key")
with c3:
    visao = st.radio("Visão:", ("Ano", "Mês", "Dia"),
                     horizontal=True, key="visao_key")
with c4:
    if metrica == "Quantidade":
        unidade = st.radio("Unidade:", ("m²", "Rolo"),
                           horizontal=True, key="unidade_qty")
    else:
        unidade = None

# -----------------------
# Cards (baseados em df_view)
# -----------------------
total_valor = float(df_view["Valor_Total"].sum()) if "Valor_Total" in df_view.columns else 0.0
clientes_unicos = int(df_view["Codcli"].nunique()) if "Codcli" in df_view.columns else 0
produtos_unicos = int(df_view["Codpro"].nunique()) if "Codpro" in df_view.columns else 0

if (metrica == "Quantidade") and ("Rolos" in df_view.columns) and ("QtdeFaturada" in df_view.columns):
    if unidade == "Rolo":
        total_quant = float(df_view["Rolos"].sum())
        label_q = "Total (Rolos)"
    else:
        total_quant = float(df_view["QtdeFaturada"].sum())
        label_q = "Total (m²)"
else:
    total_quant, label_q = 0.0, "Total"

k1, k2, k3, k4 = st.columns(4)
with k1:
    with st.container(border=True):
        st.metric("Clientes Únicos", f"{clientes_unicos:,}".replace(",", "."))
with k2:
    with st.container(border=True):
        st.metric("Produtos Únicos", f"{produtos_unicos:,}".replace(",", "."))
with k3:
    with st.container(border=True):
        st.metric(label_q, f"{total_quant:,.0f}".replace(",", "."))
with k4:
    with st.container(border=True):
        st.metric("Valor Total", f"R$ {total_valor:,.0f}".replace(",", "."))

# -----------------------
# (Opcional) Quem vendeu para quem?
# -----------------------
with st.expander("Vendedores por Cliente (resultado atual)"):
    if "Nome_Vendedor" in df_view.columns:
        mapa_cli_vend = (
            df_view.groupby("Nome_do_Cliente")["Nome_Vendedor"]
            .apply(lambda s: ", ".join(sorted(set([v for v in s if isinstance(v, str) and v.strip()])))))
        resumo = mapa_cli_vend.reset_index().rename(columns={"Nome_do_Cliente": "Cliente", "Nome_Vendedor": "Vendedor(es)"})
        st.dataframe(resumo, use_container_width=True, hide_index=True)
    else:
        st.info("Coluna Nome_Vendedor não disponível nos dados.")

# -----------------------
# Pivot simples
# -----------------------
if metrica == "Valor":
    col_valor = "Valor_Total"
    titulo_metrica = "Valor"
else:
    col_valor = "QtdeFaturada" if (unidade != "Rolo") else "Rolos"
    titulo_metrica = f"Quantidade ({'m²' if unidade != 'Rolo' else 'Rolo'})"

map_ag = {"Cliente": "Nome_do_Cliente", "Produto": "Descricao_do_Produto", "UF": "UF"}
col_ag = map_ag[agrupamento]

if visao == "Ano":
    col_visao = "Ano"
elif visao == "Mês":
    col_visao = "Mes"
else:
    col_visao = "Dia"

pivot = pd.pivot_table(
    df_view,
    values=col_valor,
    index=col_ag,
    columns=col_visao,
    aggfunc="sum",
    fill_value=0
)

if visao == "Mês":
    pivot.columns = [NOME_MESES.get(m, m) for m in pivot.columns]

pivot["Total"] = pivot.sum(axis=1)
pivot = pivot.sort_values(by="Total", ascending=False)

total_geral = pivot.sum(numeric_only=True).to_frame().T
total_geral.index = ["Total Geral"]

st.write("---")
st.subheader(f"Análise de {titulo_metrica} por {agrupamento} e {visao}")
st.dataframe(total_geral.style.format(fmt), use_container_width=True, hide_index=False)
st.dataframe(pivot.style.format(fmt), use_container_width=True, hide_index=False)

# -----------------------
# Exportações
# -----------------------
col_e1, col_e2 = st.columns(2)
with col_e1:
    st.download_button(
        "⬇️ Baixar dados filtrados (CSV)",
        data=df_view.to_csv(index=False).encode("utf-8-sig"),
        file_name="vendas_filtrado.csv",
        mime="text/csv",
    )
with col_e2:
    st.download_button(
        "⬇️ Baixar pivot (CSV)",
        data=pivot.reset_index().to_csv(index=False).encode("utf-8-sig"),
        file_name="vendas_pivot.csv",
        mime="text/csv",
    )
