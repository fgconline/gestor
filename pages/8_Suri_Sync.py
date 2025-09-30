import streamlit as st
import pandas as pd
import sqlite3
import requests
import time
import os
from utils import padronizar_telefone

# --- BLOCO DE CONTROLE DE ACESSO ---
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
    if st.session_state.get("role") == "Master": return
    if "permissions" not in st.session_state or st.session_state.permissions is None:
        st.session_state["permissions"] = get_user_permissions_from_db(st.session_state.get("role"))
    if page_name not in st.session_state.get("permissions", []):
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()
check_permission()
# --- FIM DO BLOCO ---

def separar_cod_e_nome(nome_completo):
    if isinstance(nome_completo, str) and '|' in nome_completo:
        partes = nome_completo.split('|', 1)
        return partes[0].strip(), partes[1].strip()
    else:
        nome_original = "" if pd.isna(nome_completo) else str(nome_completo)
        return None, nome_original.strip()

st.set_page_config(page_title="Sincronização Suri", page_icon="🔄", layout="wide")
st.title("🔄 Importação de Contatos do Suri")
st.markdown("---")

# --- SEÇÃO DE CONFIGURAÇÃO (AGORA USANDO st.secrets) ---
st.subheader("1. Configurações da API do Suri")
st.info("As credenciais da API são gerenciadas através dos Segredos (Secrets) do Streamlit.")

try:
    # Carrega as credenciais a partir dos segredos
    endpoint = st.secrets.suri_api.endpoint
    token = st.secrets.suri_api.token
    channel_id = st.secrets.suri_api.channel_id
    st.success("Credenciais da API do Suri carregadas com sucesso!")
except Exception as e:
    st.error("Não foi possível carregar as credenciais da API do Suri. Verifique se o arquivo `secrets.toml` está configurado corretamente para o ambiente local ou se os segredos foram adicionados no Streamlit Community Cloud.")
    st.stop()


# --- SEÇÃO DE IMPORTAÇÃO ---
st.subheader("2. Importar Contatos do Suri para o Gestor")
st.info("Esta operação irá substituir todos os dados da tabela 'suri' com os dados mais recentes da API.")

if st.button("Iniciar Importação do Suri", type="primary"):
    if not all([endpoint, token, channel_id]):
        st.warning("As credenciais da API não estão completas. Verifique a configuração de segredos.")
    else:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # ETAPA 1: BUSCAR CONTATOS
        with st.spinner("Etapa 1/3: Buscando todos os contatos..."):
            all_contacts = []
            page_num, continuation_token = 1, None
            url_list = f"{endpoint.strip('/')}/api/contacts/list"
            while True:
                st.info(f"Buscando página {page_num}...")
                body = {"orderBy": "dateCreated", "orderType": "asc", "limit": 100, "channelId": channel_id}
                if continuation_token: body["continuationToken"] = continuation_token
                try:
                    response = requests.post(url_list, headers=headers, json=body, timeout=60)
                    if response.status_code != 200: 
                        st.error(f"Erro ao buscar contatos. Status: {response.status_code}")
                        st.json(response.json())
                        break
                    data = response.json().get("data", {})
                    contacts_page, continuation_token = data.get("items", []), data.get("continuationToken")
                    if contacts_page: all_contacts.extend(contacts_page)
                    if not continuation_token: break
                    page_num += 1
                    time.sleep(1)
                except Exception as e:
                    st.error(f"Erro de conexão na Etapa 1: {e}")
                    all_contacts = [] # Limpa a lista em caso de erro
                    break
            if all_contacts:
                st.success(f"Etapa 1 concluída: {len(all_contacts)} contatos baixados.")
        
        # ETAPA 2: BUSCAR NOMES DOS ATENDENTES
        agent_map = {}
        if all_contacts:
            with st.spinner("Etapa 2/3: Buscando nomes dos atendentes..."):
                try:
                    url_users = f"{endpoint.strip('/')}/api/attendants"
                    response_users = requests.get(url_users, headers=headers, timeout=60)
                    if response_users.status_code == 200:
                        users_data = response_users.json().get("data", [])
                        agent_map = {user['id']: user['name'] for user in users_data if 'id' in user and 'name' in user}
                        st.success("Etapa 2 concluída: Nomes dos atendentes carregados.")
                    else:
                        st.warning(f"Não foi possível buscar a lista de atendentes (Status: {response_users.status_code}). A coluna 'Ultimo_Atendente' ficará vazia.")
                except Exception as e:
                    st.error(f"Erro de conexão na Etapa 2: {e}")

        # ETAPA 3: PROCESSAR E SALVAR
        if all_contacts:
            with st.spinner("Etapa 3/3: Processando e salvando dados..."):
                df_suri = pd.DataFrame(all_contacts)
                
                df_suri['telefone_suri'] = df_suri['phone']
                df_suri['Numero'] = df_suri['phone'].apply(padronizar_telefone)

                if 'agent' in df_suri.columns and agent_map:
                    df_suri['agent_id'] = df_suri['agent'].apply(lambda a: a.get('platformUserId') if isinstance(a, dict) else None)
                    df_suri['Ultimo_Atendente'] = df_suri['agent_id'].map(agent_map)
                else:
                    df_suri['Ultimo_Atendente'] = None

                df_suri[['codcli', 'Nome']] = df_suri['name'].apply(lambda x: pd.Series(separar_cod_e_nome(x)))
                map_cols = {'id': 'suri_id', 'gender': 'Genero', 'channelId': 'Id_Canal', 'channelType': 'Tipo_Canal','note': 'Observacao', 'email': 'Email', 'dateCreate': 'Primeiro_Contato', 'lastActivity': 'Ultima_Atividade'}
                df_suri = df_suri.rename(columns=map_cols)
                
                for col in ['Primeiro_Contato', 'Ultima_Atividade']:
                    df_suri[col] = pd.to_datetime(df_suri[col], errors='coerce')
                
                df_suri['Hora_Primeiro_Contato'] = df_suri['Primeiro_Contato'].dt.strftime('%H:%M:%S')
                
                for col in ['Primeiro_Contato', 'Ultima_Atividade']:
                    df_suri[col] = df_suri[col].dt.strftime('%d/%m/%Y')
                
                df_suri['Documento_Identificacao'] = None
                
                final_cols = ['suri_id', 'telefone_suri', 'Numero', 'Documento_Identificacao', 'Genero', 'Id_Canal', 'Tipo_Canal', 'Primeiro_Contato', 'Hora_Primeiro_Contato', 'Ultima_Atividade', 'Observacao', 'codcli', 'Nome', 'Email', 'Ultimo_Atendente']
                df_suri = df_suri.reindex(columns=final_cols)
                
                conn = sqlite3.connect("gestor_mkt.db")
                df_suri.to_sql('suri', conn, if_exists='replace', index=False)
                conn.close()
                st.success(f"**Importação Concluída!** {len(df_suri)} contatos salvos.")

                st.markdown("---")
                st.subheader("Verificação dos Dados Salvos")
                st.dataframe(df_suri[['Numero', 'Nome', 'Email', 'Ultimo_Atendente']].head(10))