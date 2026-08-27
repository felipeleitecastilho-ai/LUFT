import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="ETL LUFT - Monitoramento", page_icon="🔴", layout="wide")

# === CSS CUSTOMIZADO (cores Luft) ===
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&family=Source+Sans+Pro:wght@300;400;600&display=swap');
    .main .block-container { max-width: 1100px; padding-top: 2rem; }
    h1, h2, h3, .stMetricLabel { font-family: 'Montserrat', sans-serif !important; }
    .luft-header { display: flex; align-items: center; gap: 16px; margin-bottom: 0; }
    .luft-logo { font-family: 'Montserrat', sans-serif; font-weight: 800; font-size: 36px; color: #ec2849; letter-spacing: -1px; }
    .luft-sub { font-family: 'Montserrat', sans-serif; font-weight: 500; font-size: 11px; color: #99A9B5; text-transform: uppercase; letter-spacing: 2px; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
    .badge-protheus { background: #3C3950; color: #ffffff; }
    .badge-silt { background: #ec2849; color: #ffffff; }
    .badge-sucesso { background: #d1fae5; color: #065f46; }
    .badge-erro { background: #fee2e2; color: #991b1b; }
    .stMetricValue { font-family: 'Montserrat', sans-serif !important; font-weight: 800 !important; }
</style>
""", unsafe_allow_html=True)

session = get_active_session()

# === HEADER ===
st.markdown('<div class="luft-header"><div><div class="luft-logo">LUFT</div><div class="luft-sub">Logistics</div></div></div>', unsafe_allow_html=True)
st.title("ETL - Painel de Monitoramento")
st.caption("Protheus + SILT → Snowflake | Camada Bronze")

# === DADOS ===
df_log = session.sql("""
    SELECT * FROM DRE_AGENTE_ALL.BRONZE.ETL_LOG 
    ORDER BY DT_INICIO DESC 
    LIMIT 200
""").to_pandas()

# === CONTROLE DE CARGA ===
df_control = session.sql("""
    SELECT API_NAME, ULTIMA_DATA_CARGA, UPDATED_AT 
    FROM DRE_AGENTE_ALL.BRONZE.ETL_CONTROL 
    ORDER BY API_NAME
""").to_pandas()

if df_log.empty:
    st.warning("Nenhum registro de execucao encontrado na tabela ETL_LOG.")
    st.stop()

# === ULTIMA EXECUCAO ===
total_hoje = df_log[df_log['DT_INICIO'] >= str(pd.Timestamp.now().date())].copy()

# Identificar fonte
def get_fonte(tabela):
    if 'SILT' in tabela:
        return 'SILT'
    return 'PROTHEUS'

if not total_hoje.empty:
    total_hoje['FONTE'] = total_hoje['NM_TABELA'].apply(get_fonte)

# === CARDS STATUS ===
col1, col2, col3, col4 = st.columns(4)

with col1:
    erros = len(total_hoje[total_hoje['DS_STATUS'] == 'ERRO']) if not total_hoje.empty else 0
    if erros == 0:
        st.metric("Status Geral", "OK", f"{len(total_hoje)} tabelas processadas")
    else:
        st.metric("Status Geral", "ERRO", f"{erros} falha(s)")

with col2:
    total_carregado = total_hoje['QT_CARREGADOS'].sum() if not total_hoje.empty else 0
    st.metric("Registros Hoje", f"{total_carregado:,.0f}".replace(",", "."))

with col3:
    duracao = total_hoje['QT_DURACAO_SEG'].sum() if not total_hoje.empty else 0
    st.metric("Duracao Total", f"{int(duracao)}s")

with col4:
    st.metric("Proxima Execucao", "06:00", "Diario")

# === SUBTOTAIS POR FONTE ===
if not total_hoje.empty:
    col_p, col_s = st.columns(2)
    protheus_hoje = total_hoje[total_hoje['FONTE'] == 'PROTHEUS']
    silt_hoje = total_hoje[total_hoje['FONTE'] == 'SILT']
    with col_p:
        qt_p = protheus_hoje['QT_CARREGADOS'].sum() if not protheus_hoje.empty else 0
        st.markdown(f'<span class="badge badge-protheus">PROTHEUS</span> {qt_p:,.0f} registros'.replace(",", "."), unsafe_allow_html=True)
    with col_s:
        qt_s = silt_hoje['QT_CARREGADOS'].sum() if not silt_hoje.empty else 0
        st.markdown(f'<span class="badge badge-silt">SILT</span> {qt_s:,.0f} registros'.replace(",", "."), unsafe_allow_html=True)

st.divider()

# === DETALHAMENTO POR TABELA ===
st.subheader("Detalhamento por Tabela")

# Filtros
filtro_fonte = st.radio("Fonte:", ["Todos", "Protheus", "SILT", "Somente Erros"], horizontal=True)

if not total_hoje.empty:
    df_display = total_hoje[['NM_TABELA', 'FONTE', 'DS_MODO', 'QT_EXTRAIDOS', 'QT_CARREGADOS', 'QT_TOTAL_TABELA', 'QT_DURACAO_SEG', 'DS_STATUS']].copy()
    df_display.columns = ['Tabela', 'Fonte', 'Modo', 'Extraidos', 'Carregados', 'Total Base', 'Duracao (s)', 'Status']
    df_display['Tabela'] = df_display['Tabela'].str.replace('DRE_AGENTE_ALL.BRONZE.', '')

    if filtro_fonte == "Protheus":
        df_display = df_display[df_display['Fonte'] == 'PROTHEUS']
    elif filtro_fonte == "SILT":
        df_display = df_display[df_display['Fonte'] == 'SILT']
    elif filtro_fonte == "Somente Erros":
        df_display = df_display[df_display['Status'] == 'ERRO']

    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("Nenhuma execucao hoje ainda.")

st.divider()

# === GRAFICO EVOLUCAO ===
st.subheader("Volume de Registros por Dia")

df_log['DATA'] = pd.to_datetime(df_log['DT_INICIO']).dt.date
df_log['FONTE'] = df_log['NM_TABELA'].apply(get_fonte)

df_diario = df_log.groupby(['DATA', 'FONTE'])['QT_CARREGADOS'].sum().reset_index()
df_pivot = df_diario.pivot(index='DATA', columns='FONTE', values='QT_CARREGADOS').fillna(0)
df_pivot = df_pivot.sort_index()

st.bar_chart(df_pivot, use_container_width=True, color=['#3C3950', '#ec2849'])

st.divider()

# === CONTROLE DE CARGA INCREMENTAL ===
st.subheader("Controle de Carga Incremental")

if not df_control.empty:
    df_ctrl_display = df_control.copy()
    df_ctrl_display.columns = ['API', 'Ultima Data Carregada', 'Atualizado em']
    st.dataframe(df_ctrl_display, use_container_width=True, hide_index=True)

st.divider()

# === HISTORICO COMPLETO ===
st.subheader("Historico de Execucoes")

df_hist = df_log[['DT_INICIO', 'NM_TABELA', 'FONTE', 'DS_MODO', 'QT_EXTRAIDOS', 'QT_CARREGADOS', 'QT_DURACAO_SEG', 'DS_STATUS', 'DS_FILTRO', 'DS_ERRO']].copy()
df_hist.columns = ['Data/Hora', 'Tabela', 'Fonte', 'Modo', 'Extraidos', 'Carregados', 'Duracao (s)', 'Status', 'Filtro', 'Erro']
df_hist['Tabela'] = df_hist['Tabela'].str.replace('DRE_AGENTE_ALL.BRONZE.', '')

status_filter = st.selectbox("Filtrar por status:", ["Todos", "SUCESSO", "ERRO"])
if status_filter != "Todos":
    df_hist = df_hist[df_hist['Status'] == status_filter]

st.dataframe(df_hist, use_container_width=True, hide_index=True)

# === ALERTAS DE ERRO ===
erros_recentes = df_log[df_log['DS_STATUS'] == 'ERRO'].head(5)
if not erros_recentes.empty:
    st.divider()
    st.subheader("Alertas Recentes")
    for _, row in erros_recentes.iterrows():
        st.error(f"**{row['NM_TABELA'].replace('DRE_AGENTE_ALL.BRONZE.', '')}** ({row['DT_INICIO']}): {row['DS_ERRO']}")


