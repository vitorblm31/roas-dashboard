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
# CONFIGURAÇÃO DE SEGURANÇA (Blindada para Nuvem)
# ==========================================
def setup_credentials():
    try:
        if "GCP_CREDENTIALS" in st.secrets:
            creds_json = json.loads(st.secrets["GCP_CREDENTIALS"], strict=False)
            with open("credenciais.json", "w") as f:
                json.dump(creds_json, f)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credenciais.json"
        else:
            caminho_local = r"C:\Users\conta\Downloads\teeva-dashboard-analytics-8c52596374b1.json"
            if os.path.exists(caminho_local):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = caminho_local
            else:
                st.error("⚠️ Erro: Credenciais não encontradas nos Secrets.")
                st.stop()
    except Exception as e:
        st.error(f"Erro na configuração das credenciais: {e}")
        st.stop()

setup_credentials()
PROPERTY_ID = "332122962"

st.set_page_config(page_title="Dashboard GA4 API - Teeva Official", layout="wide", page_icon="📊")

# --- BARRA LATERAL (SIDEBAR) ---
st.sidebar.title("📊 Teeva Official")
st.sidebar.markdown("---")

# Filtro de Data
st.sidebar.header("Filtros de Data")
date_filter = st.sidebar.selectbox("Período", ["Últimos 7 dias", "Últimos 28 dias", "Último Ano", "Personalizado"])

if date_filter == "Últimos 7 dias": start_date, end_date = "7daysAgo", "today"
elif date_filter == "Últimos 28 dias": start_date, end_date = "28daysAgo", "today"
elif date_filter == "Último Ano": start_date, end_date = "365daysAgo", "today"
else:
    col1, col2 = st.sidebar.columns(2)
    start_date = col1.date_input("Início", datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = col2.date_input("Fim", datetime.today()).strftime("%Y-%m-%d")

# --- FUNÇÃO DE BUSCA GA4 ---
@st.cache_data(ttl=3600) 
def fetch_ga4_data(start_date, end_date):
    client = BetaAnalyticsDataClient()
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="sessionCampaignName"), Dimension(name="sessionSourceMedium")],
        metrics=[Metric(name="sessions"), Metric(name="advertiserAdCost"), Metric(name="totalRevenue")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
    )
    response = client.run_report(request)
    data = []
    for row in response.rows:
        data.append({
            "Campanha": row.dimension_values[0].value,
            "Origem": row.dimension_values[1].value,
            "Sessões": int(row.metric_values[0].value),
            "Custo": float(row.metric_values[1].value),
            "Receita": float(row.metric_values[2].value)
        })
    return pd.DataFrame(data)

# --- CARREGAR DADOS ---
st.title("Painel de Desempenho e ROAS")
df = fetch_ga4_data(start_date, end_date)

if not df.empty:
    df = df[~((df['Custo'] == 0) & (df['Receita'] == 0))]
    
    # --- BARRA DE DIVISÃO E TIPO DE VISÃO ---
    st.sidebar.markdown("---")
    st.sidebar.header("Tipo de Visão")
    visao = st.sidebar.radio("Selecione o escopo:", ["Visão Geral", "Mídia Paga"])
    
    if visao == "Mídia Paga":
        df = df[df['Custo'] > 0]
        if df.empty:
            st.info("Nenhuma campanha com custo registrada neste período.")
            st.stop()

    df['ROAS_num'] = np.where(df['Custo'] > 0, df['Receita'] / df['Custo'], np.nan)
    df['ROAS_num'] = df['ROAS_num'].round(2)

    # --- BARRA DE DIVISÃO E FILTRO DE CAMPANHA ---
    st.sidebar.markdown("---")
    st.sidebar.header("Filtro de Campanha")
    campanhas_lista = ["Todas"] + sorted(df['Campanha'].unique().tolist())
    campanha_selecionada = st.sidebar.selectbox("Filtrar Campanha", campanhas_lista)
    
    if campanha_selecionada != "Todas":
        df = df[df['Campanha'] == campanha_selecionada]

    df_filtered = df.sort_values(by="ROAS_num", ascending=False, na_position='last')

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sessões", f"{df_filtered['Sessões'].sum():,}")
    col2.metric("Custo", f"R$ {df_filtered['Custo'].sum():,.2f}")
    col3.metric("Receita", f"R$ {df_filtered['Receita'].sum():,.2f}")
    col4.metric("ROAS Médio", f"{df_filtered['Receita'].sum() / df_filtered['Custo'].sum() if df_filtered['Custo'].sum() > 0 else 0:.2f}x")

    st.markdown("### Detalhamento")
    
    df_display = df_filtered[['Campanha', 'Origem', 'Sessões', 'Custo', 'Receita', 'ROAS_num']].copy()
    df_display['ROAS'] = df_display['ROAS_num'].apply(lambda v: "Orgânico" if pd.isna(v) else f"{v:.2f}x")

    def colorir(val):
        if pd.isna(val): return ""
        return "background-color: rgba(255, 75, 75, 0.3); color: white;" if val < 1 else "background-color: rgba(40, 167, 69, 0.3); color: white;"

    styled = df_display[['Campanha', 'Origem', 'Sessões', 'Custo', 'Receita', 'ROAS']].style.apply(
        lambda _: df_display['ROAS_num'].map(colorir), subset=['ROAS']
    ).format({'Custo': 'R$ {:.2f}', 'Receita': 'R$ {:.2f}'})

    st.dataframe(styled, use_container_width=True, height=500)
else:
    st.info("Nenhum dado encontrado para este período.")
