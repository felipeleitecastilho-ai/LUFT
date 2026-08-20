import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="ETL Protheus - Monitoramento", page_icon="📊", layout="wide")

session = get_active_session()

# === HEADER ===
st.title("📊 ETL Protheus - Painel de Monitoramento")
st.caption("LUFT Solutions | Oracle/Totvs → Snowflake")

# === DADOS ===
df_log = session.sql("""
    SELECT * FROM DRE_AGENTE_ALL.BRONZE.ETL_LOG 
    ORDER BY DT_INICIO DESC 
    LIMIT 100
""").to_pandas()

if df_log.empty:
    st.warning("Nenhum registro de execução encontrado na tabela ETL_LOG.")
    st.stop()

# === ULTIMA EXECUCAO ===
ultima_exec = df_log['DT_INICIO'].max()
total_hoje = df_log[df_log['DT_INICIO'] >= str(pd.Timestamp.now().date())].copy()

# === CARDS STATUS ===
col1, col2, col3, col4 = st.columns(4)

with col1:
    erros = len(total_hoje[total_hoje['DS_STATUS'] == 'ERRO']) if not total_hoje.empty else 0
    if erros == 0:
        st.metric("Status Geral", "✅ OK", f"{len(total_hoje)} tabelas processadas")
    else:
        st.metric("Status Geral", "❌ ERRO", f"{erros} falha(s)")

with col2:
    total_carregado = total_hoje['QT_CARREGADOS'].sum() if not total_hoje.empty else 0
    st.metric("Registros Hoje", f"{total_carregado:,.0f}".replace(",", "."))

with col3:
    duracao = total_hoje['QT_DURACAO_SEG'].sum() if not total_hoje.empty else 0
    st.metric("Duração Total", f"{duracao}s")

with col4:
    st.metric("Próxima Execução", "06:00", "Diário")

st.divider()

# === DETALHAMENTO POR TABELA (ULTIMA EXECUCAO) ===
st.subheader("Detalhamento por Tabela (Última Execução)")

if not total_hoje.empty:
    df_display = total_hoje[['NM_TABELA', 'DS_MODO', 'QT_EXTRAIDOS', 'QT_DELETADOS', 'QT_CARREGADOS', 'QT_TOTAL_TABELA', 'QT_DURACAO_SEG', 'DS_STATUS']].copy()
    df_display.columns = ['Tabela', 'Modo', 'Extraídos', 'Deletados', 'Carregados', 'Total Base', 'Duração (s)', 'Status']
    df_display['Tabela'] = df_display['Tabela'].str.replace('DRE_AGENTE_ALL.BRONZE.', '')
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("Nenhuma execução hoje ainda.")

st.divider()

# === GRAFICO EVOLUCAO ===
st.subheader("Volume de Registros Carregados por Dia")

df_log['DATA'] = pd.to_datetime(df_log['DT_INICIO']).dt.date
df_diario = df_log.groupby('DATA')['QT_CARREGADOS'].sum().reset_index()
df_diario.columns = ['Data', 'Registros']
df_diario = df_diario.sort_values('Data')

st.bar_chart(df_diario.set_index('Data'), use_container_width=True)

st.divider()

# === HISTORICO COMPLETO ===
st.subheader("Histórico de Execuções")

df_hist = df_log[['DT_INICIO', 'NM_TABELA', 'DS_MODO', 'QT_EXTRAIDOS', 'QT_DELETADOS', 'QT_CARREGADOS', 'QT_DURACAO_SEG', 'DS_STATUS', 'DS_FILTRO', 'DS_ERRO']].copy()
df_hist.columns = ['Data/Hora', 'Tabela', 'Modo', 'Extraídos', 'Deletados', 'Carregados', 'Duração (s)', 'Status', 'Filtro', 'Erro']
df_hist['Tabela'] = df_hist['Tabela'].str.replace('DRE_AGENTE_ALL.BRONZE.', '')

# Filtro por status
status_filter = st.selectbox("Filtrar por status:", ["Todos", "SUCESSO", "ERRO"])
if status_filter != "Todos":
    df_hist = df_hist[df_hist['Status'] == status_filter]

st.dataframe(df_hist, use_container_width=True, hide_index=True)

# === ALERTAS DE ERRO ===
erros_recentes = df_log[df_log['DS_STATUS'] == 'ERRO'].head(5)
if not erros_recentes.empty:
    st.divider()
    st.subheader("⚠️ Erros Recentes")
    for _, row in erros_recentes.iterrows():
        st.error(f"**{row['NM_TABELA'].replace('DRE_AGENTE_ALL.BRONZE.', '')}** ({row['DT_INICIO']}): {row['DS_ERRO']}")
