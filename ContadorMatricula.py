# ContadorMatricula.py
# -*- coding: utf-8 -*-
import os
import json
import time
import datetime as dt
import pandas as pd
import requests
import urllib3
import streamlit as st
import altair as alt
from requests.auth import HTTPBasicAuth
from collections import defaultdict

# =========================
# Configurações fixas (sem secrets)
# =========================
st.set_page_config(page_title="Matrículas por Unidade — SMP.0025", page_icon="📊", layout="wide")

# Desabilitar avisos SSL (use apenas se seu ambiente exigir verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Credenciais e Endpoint TOTVS (FIXOS NESTE ARQUIVO)
USERNAME = "p_heflo"
PASSWORD = "Q0)G$sW]rj"
BASE_URL = "https://raizeducacao160286.rm.cloudtotvs.com.br:8051/api/framework/v1/consultaSQLServer/RealizaConsulta"

# Consulta nomeada cadastrada no servidor (com DECLARE fixo interno)
QUERY_NAME = "SMP.0025"
QUERY_VERSION = 0
QUERY_SCOPE = "S"  # "S" (Server)

# =========================
# Funções
# =========================
@st.cache_data(ttl=5 * 60, show_spinner=False)
def executar_smp0025():
    """
    Executa SMP.0025 sem parâmetros (DECLARE está dentro da query no servidor).
    Retorna (df, meta):
      - df: DataFrame com colunas ['Filial', 'Matrículas']
      - meta: dict com metadados da requisição/resposta
    """
    url = f"{BASE_URL}/{QUERY_NAME}/{QUERY_VERSION}/{QUERY_SCOPE}"
    params = {}  # sem "parameters", pois DECLARE é interno

    t0 = time.perf_counter()
    resp = requests.get(
        url,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        params=params,
        verify=False,      # cuidado em produção; ideal é manter SSL válido e verify=True
        timeout=120
    )
    elapsed = time.perf_counter() - t0

    meta = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "method": "GET",
        "url": resp.request.url if resp.request else url,
        "query_params": params,
        "status_code": resp.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "request_headers": dict(resp.request.headers) if resp.request and resp.request.headers else {},
        "response_headers": dict(resp.headers) if resp.headers else {},
    }
    for k in ("X-Request-Id", "X-Correlation-Id", "request-id", "correlation-id"):
        if k in resp.headers:
            meta[k] = resp.headers.get(k)

    if resp.status_code != 200:
        meta["error_body"] = resp.text[:2000] if resp.text else ""
        raise RuntimeError(f"Erro HTTP {resp.status_code} ao executar {QUERY_NAME}")

    try:
        dados = resp.json()
    except Exception:
        meta["error_body"] = resp.text[:2000] if resp.text else ""
        raise RuntimeError("Resposta não é JSON válido.")

    if not isinstance(dados, list):
        raise RuntimeError(f"Formato inesperado: esperado lista, obtido {type(dados)}")

    # Normalização para ['Filial','Matrículas']
    agg = defaultdict(int)
    for item in dados:
        filial = (item.get("FILIAL") or item.get("Filial") or item.get("NOMEFANTASIA") or "").strip()
        # Substituir "COLEGIO E CURSO MATRIZ EDUCACAO" por ""
        filial = filial.replace("COLEGIO E CURSO MATRIZ EDUCACAO", "").strip()
        matr = item.get("MATRICULAS") or item.get("Matriculas") or item.get("QTD") or 0
        try:
            matr = int(float(matr))
        except Exception:
            matr = 0
        if filial:
            agg[filial] += matr

    rows = [{"Filial": k, "Matrículas": v} for k, v in agg.items()]
    df = pd.DataFrame(rows)

    return df, meta


def chart_barras(df: pd.DataFrame):
    if df.empty:
        return alt.Chart(pd.DataFrame({"Filial": [], "Matrículas": []})).mark_bar()
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("Matrículas:Q", title="Matrículas"),
            y=alt.Y("Filial:N", sort="-x", title=None),
            tooltip=["Filial", "Matrículas"]
        )
        .properties(height=max(260, 28 * len(df)))
        .interactive()
    )

# =========================
# UI
# =========================

# Atualização automática a cada 10 segundos
if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = time.time()
if time.time() - st.session_state["last_refresh"] > 10:
    st.session_state["last_refresh"] = time.time()
    st.experimental_rerun()

# Execução
try:
    with st.spinner("Consultando TOTVS…"):
        df, meta = executar_smp0025()
except Exception as e:
    st.error(f"Falha ao executar a consulta: {e}")
    st.stop()


# Métricas
total_matriculas = int(df["Matrículas"].sum()) if not df.empty else 0

m1, m2, m3 = st.columns(3)
m1.metric("Total de matrículas", f"{total_matriculas:,}".replace(",", "."))
m3.metric("Atualizado em", dt.datetime.now().strftime("%d/%m/%Y %H:%M"))

# Tabela + download
st.subheader("Tabela")
st.dataframe(df.reset_index(drop=True), use_container_width=True)

csv = df.to_csv(index=False, sep=";").encode("utf-8-sig")


# Rodapé leve
st.markdown(
    "<div style='color:#667085;font-size:12px;margin-top:12px;'>BI - Matriz Educação</div>",
    unsafe_allow_html=True
)
