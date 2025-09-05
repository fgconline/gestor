# --------------------------------------------
# dados.py  |  Importação Centralizada
# --------------------------------------------
import streamlit as st
import pandas as pd
import sqlite3
import re
import unicodedata
import os
from io import BytesIO, StringIO
from datetime import datetime

# ============ CONFIG INICIAL (sempre antes de qualquer st.*) ============
st.set_page_config(page_title="Dados | Importação", layout="wide")

# ============ PARÂMETROS GERAIS ============
# Fallback robusto para DB_PATH: secrets -> env -> ./gestor.db
DEFAULT_DB_PATH = os.path.join(os.getcwd(), "gestor.db")
try:
    DB_PATH = st.secrets["DB_PATH"]  # pode disparar StreamlitSecretNotFoundError
except Exception:
    DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)

# ============ FUNÇÕES AUXILIARES ============
def criar_conexao():
    # isola conexão por chamada (boas práticas com Streamlit)
    return sqlite3.connect(DB_PATH)

def sem_acentos(s: str) -> str:
    if s is None:
        return s
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

def sanitizar_nome_coluna(nome_coluna: str) -> str:
    nome_coluna = sem_acentos(str(nome_coluna).strip())
    for char in " /-.()[]{}|":
        nome_coluna = nome_coluna.replace(char, "_")
    while "__" in nome_coluna:
        nome_coluna = nome_coluna.replace("__", "_")
    return nome_coluna.strip("_")

def normaliza_numeric_str(x):
    # Converte string "1.234,56" -> 1234.56; retorna float ou None
    if pd.isna(x):
        return None
    s = str(x).strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def garantir_tabela_clientes():
    ddl = """
    CREATE TABLE IF NOT EXISTS clientes (
        CodCli     INTEGER PRIMARY KEY,
        Nome       TEXT NOT NULL,
        Email      TEXT,
        Estado     TEXT,
        Cidade     TEXT,
        Fone       TEXT,
        CodSeg     INTEGER,
        NomeSeg    TEXT,
        CodTag     TEXT
    );
    """
    idx = [
        "CREATE INDEX IF NOT EXISTS ix_clientes_nome    ON clientes (Nome);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_email   ON clientes (Email);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_estado  ON clientes (Estado);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_cidade  ON clientes (Cidade);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_codseg  ON clientes (CodSeg);",
        "CREATE INDEX IF NOT EXISTS ix_clientes_codtag  ON clientes (CodTag);",
    ]
    with criar_conexao() as conn:
        cur = conn.cursor()
        cur.execute(ddl)
        for sql in idx:
            cur.execute(sql)
        conn.commit()

def garantir_indices_vendas():
    # Garante índice único para funcionar o upsert por (Data_NF, Num_NF, Codpro)
    with criar_conexao() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                Data_NF TEXT,
                Num_NF  TEXT,
                Codpro  TEXT
            );
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_vendas
            ON vendas (Data_NF, Num_NF, Codpro);
        """)
        conn.commit()

# ============ LOGIN / PERMISSÃO ============
# Ajuste conforme seu app. Se não usar login nesta página, deixe como True.
if not st.session_state.get("logged_in", True):
    st.error("Por favor, faça o login para acessar esta página.")
    st.stop()

# ============ TÍTULO / INFO ============
st.title("💾 Dados: Importação Centralizada")
st.write("Arraste e solte um ou mais arquivos no campo abaixo.")
st.info(
    "Arquivos reconhecidos: `lucratividade_...` (vendas), `produtos.xlsx`, "
    "`pedidos.xls`, `imports.xlsx`, `hub*.txt/xls` (estoques), `metas*.csv` e **`clientes.csv`**."
)

# Garante estruturas essenciais
garantir_tabela_clientes()
garantir_indices_vendas()

# ============ UPLOADER ÚNICO ============
arquivos_enviados = st.file_uploader(
    "Selecione um ou mais arquivos para importar",
    type=["txt", "csv", "xlsx", "xls"],
    accept_multiple_files=True
)

# (Opcional) parâmetros de leitura CSV
with st.expander("⚙️ Opções de leitura (CSV)", expanded=False):
    csv_sep = st.text_input("Separador (CSV)", value=";")
    csv_encoding = st.text_input("Encoding (CSV)", value="latin1")

# ============ LOOP DE PROCESSAMENTO ============
if arquivos_enviados:
    st.write("---")
    for arquivo in arquivos_enviados:
        nome_arquivo = arquivo.name
        nome_lower = nome_arquivo.lower()

        # 1) VENDAS: lucratividade_*.txt
        if nome_lower.startswith("lucratividade_"):
            with st.expander(f"Processando Vendas: `{nome_arquivo}`", expanded=True):
                try:
                    df = pd.read_csv(arquivo, sep=';', encoding='latin1', dtype=str, skipinitialspace=True)
                    df.columns = [sanitizar_nome_coluna(col) for col in df.columns]

                    # remove colunas Unnamed
                    colunas_para_remover = [col for col in df.columns if 'unnamed' in col.lower()]
                    if colunas_para_remover:
                        df = df.drop(columns=colunas_para_remover)

                    with st.spinner("Limpando dados de vendas..."):
                        # normaliza zeros à esquerda em chaves comuns
                        for col in ['Num_NF', 'CFOP', 'Repr', 'Codcli', 'Codpro', 'Vend']:
                            if col in df.columns:
                                df[col] = df[col].astype(str).str.lstrip('0').str.strip()

                        # data
                        if 'Data_NF' in df.columns:
                            df['Data_NF'] = pd.to_datetime(
                                df['Data_NF'], format='%d/%m/%Y', errors='coerce'
                            )
                        else:
                            st.error("Coluna 'Data_NF' não encontrada.")
                            st.stop()

                        # detecta colunas textuais (mantidas como texto)
                        colunas_de_texto = set(map(str.lower, [
                            'Repr', 'Nome_Representante', 'Nome_do_Cliente', 'UF',
                            'Descricao_Classif', 'Descricao_Sub_Classf', 'Referencia',
                            'Descricao_do_Produto', 'UM', 'Prz', 'Prazo_Medio', 'Frt',
                            'Municipio', 'Vend', 'Nome_do_Vendedor', 'PlacaVei',
                            'Unidade_Faturamento', 'Empresa', 'DescricaoDoCFOP',
                            'descricao_da_natureza_de_operacao', 'CNPJr_rl_CPF',
                            'Num_NF', 'Codcli', 'Codpro', 'CFOP'
                        ]))

                        # converte numéricas
                        for col in df.columns:
                            if col.lower() not in colunas_de_texto and col.lower() != 'data_nf':
                                df[col] = df[col].apply(normaliza_numeric_str)

                        # preenche só numéricas com 0
                        for col in df.columns:
                            if df[col].dtype in [float, int]:
                                df[col] = df[col].fillna(0)

                        # dedup por (Data_NF, Num_NF, Codpro)
                        subset_cols = [c for c in ['Data_NF', 'Num_NF', 'Codpro'] if c in df.columns]
                        if len(subset_cols) == 3:
                            df.drop_duplicates(subset=subset_cols, keep='first', inplace=True)

                    st.success(f"Arquivo `{nome_arquivo}` lido e limpo com sucesso.")
                    st.dataframe(df.head())

                    if st.button(f"Atualizar Vendas com `{nome_arquivo}`", key=f"btn_vendas_{nome_arquivo}"):
                        df = df.dropna(subset=['Data_NF'])
                        if not df.empty:
                            with st.spinner("Atualizando banco de Vendas (upsert)..."):
                                conn = criar_conexao()
                                cursor = conn.cursor()

                                cols = df.columns.tolist()
                                cols_sql = ', '.join([f'"{c}"' for c in cols])
                                placeholders = ', '.join(['?'] * len(cols))

                                # atualiza tudo exceto as chaves
                                update_cols = [f'"{c}" = excluded."{c}"' for c in cols if c not in ['Data_NF', 'Num_NF', 'Codpro']]
                                update_sql = ', '.join(update_cols) if update_cols else ''

                                sql = f"""
                                INSERT INTO vendas ({cols_sql}) VALUES ({placeholders})
                                ON CONFLICT(Data_NF, Num_NF, Codpro) DO UPDATE SET {update_sql};
                                """

                                # Data_NF -> ISO
                                df['Data_NF'] = pd.to_datetime(df['Data_NF']).dt.strftime('%Y-%m-%d')

                                data_tuples = list(df.itertuples(index=False, name=None))
                                cursor.executemany(sql, data_tuples)

                                conn.commit()
                                conn.close()
                                st.success("Banco de Vendas atualizado com sucesso!")
                                st.cache_data.clear()
                        else:
                            st.warning("Nenhum dado válido para inserir.")

                except Exception as e:
                    st.error(f"Erro em `{nome_arquivo}`: {e}")

        # 2) PRODUTOS: produtos.xlsx
        elif nome_lower == 'produtos.xlsx':
            with st.expander(f"Processando Produtos: `{nome_arquivo}`", expanded=True):
                try:
                    df_prod = pd.read_excel(arquivo)
                    df_prod.columns = [sanitizar_nome_coluna(c) for c in df_prod.columns]
                    st.success(f"Arquivo de Produtos `{nome_arquivo}` lido.")
                    st.dataframe(df_prod.head())
                    if st.button(f"Atualizar Produtos com `{nome_arquivo}`", key=f"btn_prod_{nome_arquivo}"):
                        with criar_conexao() as conn:
                            df_prod.to_sql('produtos', conn, if_exists='replace', index=False)
                        st.success("Produtos atualizados!")
                        st.cache_data.clear()
                except Exception as e:
                    st.error(f"Erro em `{nome_arquivo}`: {e}")

        # 3) PEDIDOS: pedidos.xls
        elif nome_lower == 'pedidos.xls':
            with st.expander(f"Processando Pedidos: `{nome_arquivo}`", expanded=True):
                try:
                    df_ped = pd.read_excel(arquivo)
                    df_ped.columns = [
                        'tipo', 'numped', 'dtpedido', 'dtentrega', 'codcli', 'nomecli',
                        'codpro', 'descricao', 'qtvend', 'vlunit', 'vlliquido',
                        'ocompra', 'vendedor', 'nome_vendedor'
                    ]
                    for col in ['dtpedido', 'dtentrega']:
                        if pd.api.types.is_numeric_dtype(df_ped[col]):
                            df_ped[col] = pd.to_datetime(df_ped[col], unit='D', origin='1899-12-30', errors='coerce').dt.date
                        else:
                            df_ped[col] = pd.to_datetime(df_ped[col], errors='coerce').dt.date

                    st.success(f"Arquivo de Pedidos `{nome_arquivo}` lido.")
                    st.dataframe(df_ped.head())

                    if st.button(f"Atualizar Pedidos com `{nome_arquivo}`", key=f"btn_ped_{nome_arquivo}"):
                        with criar_conexao() as conn:
                            df_ped.to_sql('pedidos', conn, if_exists='replace', index=False)
                        st.success("Pedidos atualizados!")
                        st.cache_data.clear()
                except Exception as e:
                    st.error(f"Erro em `{nome_arquivo}`: {e}")

        # 4) IMPORTAÇÕES: imports.xlsx (aba Import)
        elif nome_lower == 'imports.xlsx':
            with st.expander(f"Processando Importações: `{nome_arquivo}`", expanded=True):
                try:
                    df_imp = pd.read_excel(arquivo, sheet_name='Import')
                    df_imp = df_imp.rename(columns={
                        'nome': 'Nome_Importacao',
                        'Data_prevista': 'Previsao_Chegada',
                        'CodPro': 'CodPro',
                        'Descrição': 'Descricao',
                        'Rolos': 'Rolos',
                        'M2': 'M2',
                        'Status_fabrica': 'Status_Fabrica',
                        'Recebido': 'Recebido',
                        'Reservado': 'Reservado'
                    })
                    db_columns = ['Nome_Importacao', 'Previsao_Chegada', 'CodPro', 'Descricao',
                                  'Rolos', 'M2', 'Status_Fabrica', 'Recebido', 'Reservado']
                    for col in db_columns:
                        if col not in df_imp.columns:
                            raise ValueError(f"Coluna esperada '{col}' não encontrada no arquivo.")
                    df_imp = df_imp[db_columns]
                    df_imp['Previsao_Chegada'] = pd.to_datetime(df_imp['Previsao_Chegada'], errors='coerce').dt.date

                    st.success(f"Arquivo de Importações `{nome_arquivo}` lido com sucesso.")
                    st.dataframe(df_imp.head())

                    if st.button(f"Atualizar Importações com `{nome_arquivo}`", key=f"btn_imp_{nome_arquivo}"):
                        with criar_conexao() as conn:
                            df_imp.to_sql('importacoes', conn, if_exists='replace', index=False)
                        st.success("Tabela de Importações atualizada!")
                        st.cache_data.clear()
                except Exception as e:
                    st.error(f"Ocorreu um erro ao processar `{nome_arquivo}`: {e}")

        # 5) ESTOQUE: hub*.txt/xls
        elif ('hub' in nome_lower) and (nome_lower.endswith('.xls') or nome_lower.endswith('.txt')):
            nome_hub_match = re.search(r"(hub\d+)", nome_lower)
            if nome_hub_match:
                nome_hub = nome_hub_match.group(1)
                coluna_db = f"Estoque_{nome_hub.replace('hub', '')}"

                with st.expander(f"Processando Estoque {nome_hub.upper()}: `{nome_arquivo}`", expanded=True):
                    try:
                        # leitura bruta
                        if nome_lower.endswith('.xls'):
                            df_bruto = pd.read_excel(arquivo, header=None)
                            linhas_brutas = df_bruto.fillna('').astype(str).agg(' '.join, axis=1).tolist()
                        else:
                            linhas_brutas = arquivo.getvalue().decode('latin1').splitlines()

                        dados_estoque = []
                        linhas_corrigidas = []
                        buffer_linha = ""

                        for linha in linhas_brutas:
                            linha_limpa = re.sub(r'\s+', ' ', str(linha)).strip()
                            if not linha_limpa or "Referencia" in linha_limpa or "TOTAL GERAL" in linha_limpa:
                                continue
                            match_quantidade = re.search(r'(\d{1,3}(\.\d{3})*,\d+)$', linha_limpa)
                            if match_quantidade:
                                buffer_linha += " " + linha_limpa
                                linhas_corrigidas.append(buffer_linha.strip())
                                buffer_linha = ""
                            else:
                                buffer_linha += " " + linha_limpa

                        if buffer_linha.strip():
                            linhas_corrigidas.append(buffer_linha.strip())

                        for linha in linhas_corrigidas:
                            partes = linha.split()
                            if len(partes) < 3:
                                continue
                            codpro_str = partes[1]
                            quantidade_str = partes[-1]
                            if codpro_str.isdigit() and 4 <= len(codpro_str) <= 7:
                                try:
                                    codpro = int(codpro_str)
                                    quantidade = float(quantidade_str.replace('.', '').replace(',', '.'))
                                    dados_estoque.append({'CodPro': codpro, coluna_db: quantidade})
                                except Exception:
                                    continue

                        if not dados_estoque:
                            st.error(f"Nenhum dado de estoque válido encontrado no arquivo `{nome_arquivo}`.")
                        else:
                            df_estoque = pd.DataFrame(dados_estoque).groupby('CodPro').sum().reset_index()
                            st.success(f"{len(df_estoque)} registros de estoque encontrados e processados.")
                            st.dataframe(df_estoque.head())

                            if st.button(f"Atualizar Estoque com `{nome_arquivo}`", key=f"btn_est_{nome_arquivo}"):
                                with st.spinner(f"Atualizando estoque de {nome_hub.upper()}..."):
                                    with criar_conexao() as conn:
                                        payload = [(int(r['CodPro']), float(r[coluna_db])) for _, r in df_estoque.iterrows()]
                                        conn.executemany(
                                            f"""INSERT INTO estoque (CodPro, {coluna_db}) VALUES (?, ?)
                                                ON CONFLICT(CodPro) DO UPDATE SET {coluna_db} = excluded.{coluna_db};""",
                                            payload
                                        )
                                        conn.commit()
                                st.success(f"Estoque de {nome_hub.upper()} atualizado!")
                                st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Ocorreu um erro ao processar `{nome_arquivo}`: {e}")

        # 6) METAS: metas*.csv
        elif nome_lower.startswith('metas') and nome_lower.endswith('.csv'):
            with st.expander(f"Processando Metas: `{nome_arquivo}`", expanded=True):
                try:
                    df_metas = pd.read_csv(arquivo, delimiter=';', encoding='latin1')
                    st.success(f"Arquivo de Metas `{nome_arquivo}` lido com sucesso.")
                    st.dataframe(df_metas.head())

                    if st.button(f"Atualizar Metas com `{nome_arquivo}`", key=f"btn_metas_{nome_arquivo}"):
                        with criar_conexao() as conn:
                            df_metas.to_sql('metas', conn, if_exists='replace', index=False)
                        st.success("Tabela de Metas atualizada!")
                        st.cache_data.clear()
                except Exception as e:
                    st.error(f"Ocorreu um erro ao processar `{nome_arquivo}`: {e}")

        # 7) CLIENTES: clientes.csv
        elif nome_lower.startswith('clientes') and nome_lower.endswith('.csv'):
            with st.expander(f"Processando Clientes: `{nome_arquivo}`", expanded=True):
                try:
                    # leitura CSV com parâmetros do expander
                    content = arquivo.read()
                    try:
                        df_cli = pd.read_csv(StringIO(content.decode(csv_encoding, errors="ignore")), sep=csv_sep)
                    except Exception:
                        df_cli = pd.read_csv(BytesIO(content), sep=csv_sep, encoding_errors="ignore")

                    # normaliza headers (remove acentos, espaços, pontuação -> underscore)
                    df_cli.columns = [sanitizar_nome_coluna(c) for c in df_cli.columns]

                    # mapeamento flexível: aceita variações nos nomes
                    alias_map = {
                        "CodCli":   {"codcli", "codigo", "cliente_id", "idcliente", "id"},
                        "Nome":     {"nome", "razao", "razao_social", "cliente_nome"},
                        "Email":    {"email", "e_mail", "mail"},
                        "Estado":   {"estado", "uf"},
                        "Cidade":   {"cidade", "municipio", "cidade_municipio"},
                        "Fone":     {"fone", "telefone", "celular", "contato"},
                        "CodSeg":   {"codseg", "segmento", "seg", "cod_segmento"},
                        "NomeSeg":  {"nomeseg", "segmento_nome", "nome_segmento"},
                        "CodTag":   {"codtag", "tag", "codigo_tag"}
                    }

                    # cria colunas padrão se faltarem (por alias)
                    for col_std in alias_map.keys():
                        if col_std not in df_cli.columns:
                            aliases = {sanitizar_nome_coluna(a) for a in alias_map[col_std]}
                            inter = set(df_cli.columns).intersection(aliases)
                            if inter:
                                df_cli.rename(columns={list(inter)[0]: col_std}, inplace=True)
                            else:
                                df_cli[col_std] = None

                    # tipagem/limpeza
                    # CodCli, CodSeg -> int (quando possível)
                    for int_col in ["CodCli", "CodSeg"]:
                        if int_col in df_cli.columns:
                            df_cli[int_col] = pd.to_numeric(df_cli[int_col], errors="coerce").astype("Int64")

                    # strings: tira espaços
                    for txt_col in ["Nome", "Email", "Estado", "Cidade", "Fone", "NomeSeg", "CodTag"]:
                        if txt_col in df_cli.columns:
                            df_cli[txt_col] = df_cli[txt_col].astype(str).fillna("").str.strip()
                            if txt_col == "Estado":
                                df_cli[txt_col] = df_cli[txt_col].str.upper().str[:2]

                    st.success(f"Arquivo de Clientes `{nome_arquivo}` lido com sucesso.")
                    st.dataframe(df_cli.head())

                    if st.button(f"Atualizar Clientes com `{nome_arquivo}`", key=f"btn_cli_{nome_arquivo}"):
                        with st.spinner("Gravando clientes (upsert por CodCli)..."):
                            with criar_conexao() as conn:
                                # garante tabela
                                garantir_tabela_clientes()
                                # upsert
                                payload = []
                                for _, r in df_cli.iterrows():
                                    payload.append((
                                        None if pd.isna(r["CodCli"]) else int(r["CodCli"]),
                                        r["Nome"] if pd.notna(r["Nome"]) else None,
                                        r["Email"] if pd.notna(r["Email"]) else None,
                                        r["Estado"] if pd.notna(r["Estado"]) else None,
                                        r["Cidade"] if pd.notna(r["Cidade"]) else None,
                                        r["Fone"] if pd.notna(r["Fone"]) else None,
                                        None if pd.isna(r["CodSeg"]) else int(r["CodSeg"]),
                                        r["NomeSeg"] if pd.notna(r["NomeSeg"]) else None,
                                        r["CodTag"] if pd.notna(r["CodTag"]) else None,
                                    ))

                                conn.executemany("""
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
                                """, payload)
                                conn.commit()
                        st.success("Clientes importados/atualizados com sucesso!")
                        st.cache_data.clear()
                except Exception as e:
                    st.error(f"Erro ao processar `{nome_arquivo}`: {e}")

        # não reconhecido
        else:
            st.warning(f"O arquivo `{nome_arquivo}` não foi reconhecido.")
