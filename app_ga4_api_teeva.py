import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import timedelta, datetime
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
)

# ==========================================
# CONFIGURAÇÕES DA API (Nuvem ou Local)
# ==========================================
try:
    # Tenta ler do Streamlit Secrets (Nuvem)
    if "GCP_CREDENTIALS" in st.secrets:
        with open("credenciais.json", "w") as f:
            json.dump(json.loads(st.secrets["GCP_CREDENTIALS"]), f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credenciais.json"
    else:
        raise Exception("Secrets não encontrados")
except Exception:
    # Se falhar (ex: rodando localmente no PC), usa o caminho do Windows
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\conta\Downloads\teeva-dashboard-analytics-8c52596374b1.json"

PROPERTY_ID = "332122962"

# Configuração da Página
st.set_page_config(page_title="Dashboard GA4 API - Teeva Official", layout="wide", page_icon="📊")

# --- BARRA LATERAL (SIDEBAR) ---
st.sidebar.title("📊 Teeva Official")
st.sidebar.markdown("---")
st.sidebar.header("Filtros de Data")

date_filter = st.sidebar.selectbox(
    "Selecione o intervalo",
    ["Últimos 7 dias", "Últimos 28 dias", "Último Ano", "Personalizado"]
)

if date_filter == "Últimos 7 dias":
    start_date = "7daysAgo"
    end_date = "today"
elif date_filter == "Últimos 28 dias":
    start_date = "28daysAgo"
    end_date = "today"
elif date_filter == "Último Ano":
    start_date = "365daysAgo"
    end_date = "today"
else:
    col1, col2 = st.sidebar.columns(2)
    with col1:
        d_start = st.date_input("Início", datetime.today() - timedelta(days=7))
    with col2:
        d_end = st.date_input("Fim", datetime.today())
    start_date = d_start.strftime("%Y-%m-%d")
    end_date = d_end.strftime("%Y-%m-%d")

# --- FUNÇÃO PARA BUSCAR DADOS NA API DO GA4 ---
@st.cache_data(ttl=3600) 
def fetch_ga4_data(property_id, start_date, end_date):
    try:
        client = BetaAnalyticsDataClient()
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[
                Dimension(name="sessionCampaignName"),
                Dimension(name="sessionSourceMedium")
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="advertiserAdCost"),
                Metric(name="totalRevenue") 
            ],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        )
        response = client.run_report(request)

        data = []
        for row in response.rows:
            data.append({
                "Campanha da sessão": row.dimension_values[0].value,
                "Origem / mídia da sessão": row.dimension_values[1].value,
                "Sessões": int(row.metric_values[0].value),
                "Custo": float(row.metric_values[1].value),
                "Receita": float(row.metric_values[2].value)
            })
        
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Erro ao conectar com a API do GA4: {e}")
        return pd.DataFrame()

# --- CARREGAR DADOS ---
st.title("Painel de Desempenho e ROAS")
    
with st.spinner("Buscando dados da API do GA4..."):
    df = fetch_ga4_data(PROPERTY_ID, start_date, end_date)

if not df.empty:
    # Remove linhas totalmente zeradas (Custo 0 e Receita 0)
    df = df[~((df['Custo'] == 0) & (df['Receita'] == 0))]

    if df.empty:
        st.info("Nenhuma campanha com custo ou receita registrada neste período.")
        st.stop()

    st.sidebar.markdown("---")
    st.sidebar.subheader("Tipo de Visão")
    visao = st.sidebar.radio("Selecione o escopo:", ["Visão Geral", "Mídia Paga"])
    
    if visao == "Mídia Paga":
        df = df[df['Custo'] > 0]
        if df.empty:
            st.info("Nenhuma campanha com custo.")
            st.stop()

    # Cálculo do ROAS numérico padrão
    df['ROAS_num'] = np.where(df['Custo'] > 0, df['Receita'] / df['Custo'], np.nan)
    df['ROAS_num'] = df['ROAS_num'].round(2)

    st.sidebar.markdown("---")
    campanha_selecionada = st.sidebar.selectbox("Filtrar:", ["Todas as Campanhas"] + df['Campanha da sessão'].unique().tolist())
    
    df_filtered = df if campanha_selecionada == "Todas as Campanhas" else df[df['Campanha da sessão'] == campanha_selecionada]

    # Ordenação automática pelo maior ROAS (jogando os nulos/orgânicos para o final)
    df_filtered = df_filtered.sort_values(by="ROAS_num", ascending=False, na_position='last')

    # Métricas gerais do topo
    custo_total = df_filtered['Custo'].sum()
    receita_total = df_filtered['Receita'].sum()
    roas_medio = receita_total / custo_total if custo_total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sessões", f"{df_filtered['Sessões'].sum():,}")
    col2.metric("Custo", f"R$ {custo_total:,.2f}")
    col3.metric("Receita", f"R$ {receita_total:,.2f}")
    col4.metric("ROAS Médio (Pago)", f"{roas_medio:.2f}x")

    # --- TABELA INTELIGENTE COM CORES NA COLUNA ROAS ---
    st.markdown("### Detalhamento de Canais e Campanhas")
    
    df_display = df_filtered[['Campanha da sessão', 'Origem / mídia da sessão', 'Sessões', 'Custo', 'Receita', 'ROAS_num']].copy()
    
    # Coluna de texto amigável
    df_display['ROAS'] = df_display['ROAS_num'].apply(lambda val: "Orgânico" if pd.isna(val) else f"{val:.2f}x")

    # Função de cores mapeada pelo valor numérico
    def colorir_roas(val):
        if pd.isna(val):
            return "" 
        elif val < 1.0:
            return "background-color: rgba(255, 75, 75, 0.3); color: white;" 
        elif val < 2.0:
            return "background-color: rgba(255, 193, 7, 0.3); color: white;" 
        else:
            return "background-color: rgba(40, 167, 69, 0.3); color: white;" 

    # Aplica as cores na coluna visível de texto baseando-se nos valores numéricos correspondentes
    colors_series = df_display['ROAS_num'].map(colorir_roas)

    styled_df = df_display[['Campanha da sessão', 'Origem / mídia da sessão', 'Sessões', 'Custo', 'Receita', 'ROAS']].style.apply(
        lambda _: colors_series, subset=['ROAS']
    ).format({
        'Custo': 'R$ {:.2f}',
        'Receita': 'R$ {:.2f}',
    })

    st.dataframe(styled_df, use_container_width=True, height=500)
else:
    st.info("Aguardando dados...")