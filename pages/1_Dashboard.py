# pages/0_Dashboard.py
import streamlit as st

st.title("🏠 Dashboard")
st.markdown("""
Bem-vindo ao **Gestor**.

Use o menu para navegar entre Vendas, Pedidos, Estoque e demais módulos.
""")

# Cards/resumos (exemplos — substitua por queries reais depois)
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Vendas Mês", "R$ 0", "0%")
with col2:
    st.metric("Pedidos Abertos", "0", "0")
with col3:
    st.metric("Itens em Falta", "0", "0")


