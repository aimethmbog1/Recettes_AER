# IMPORTER LES BIBLIOTHÈQUES
import streamlit as st
from datetime import date
import yfinance as yf
from prophet import prophet
from prophet.plot import plot_plotly
import plotly.graph_objects as go

import pandas as pd
import os
import matplotlib.pyplot as plt
import seaborn as sns
import altair as alt
import time



# CONFIGURATION DE LA PAGE
st.set_page_config(
    page_title="Tableau de Bord AER",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Essayer d’importer folium, sinon désactiver la cartographie
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ModuleNotFoundError:
    FOLIUM_AVAILABLE = False
    st.warning("🚫 folium non installé : la cartographie est désactivée.")

# ---------------- CACHE DES DONNÉES ----------------
@st.cache_data(ttl=300)
def load_data():
    # Chargement et transformation de Classeur1.xlsx
    raw = pd.read_excel("Classeur1.xlsx", dtype=str)
    df_cons = (
        raw
        .melt(var_name="Localité", value_name="Meter SN")
        .dropna(subset=["Meter SN"])
    )
    df_cons["Meter SN"] = df_cons["Meter SN"].str.strip().str.replace(" ", "", regex=False)

    # Chargement et nettoyage de recharge1.xlsx
    df_rech = pd.read_excel("recharge1.xlsx", dtype=str)
    df_rech = df_rech.rename(columns={"Recharge": "Meter SN", "Montant": "Montant"})
    df_rech = df_rech.dropna(subset=["Meter SN", "Montant"])
    df_rech["Meter SN"] = df_rech["Meter SN"].str.strip().str.replace(" ", "", regex=False)
    df_rech["Montant"] = (
        df_rech["Montant"]
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )
    # Conversion date si présente
    if "Date" in df_rech.columns:
        df_rech["Date"] = pd.to_datetime(df_rech["Date"], errors="coerce")
    return df_cons, df_rech

# ---------------- VÉRIFICATION DES FICHIERS ----------------
if not os.path.exists("Classeur1.xlsx") or not os.path.exists("recharge1.xlsx"):
    st.error("❌ Les fichiers 'Classeur1.xlsx' et 'recharge1.xlsx' sont introuvables.")
    st.stop()

df_cons, df_rech = load_data()

# ---------------- HEADER ----------------
st.markdown("""
<div style="background-color:#004080;padding:10px;border-radius:5px">
    <h1 style="color:white;text-align:center;">📊 Tableau de Bord AER – Recettes par Localité</h1>
</div>
""", unsafe_allow_html=True)

# ---------------- SIDEBAR – FILTRES ----------------
st.sidebar.header("🔍 Filtres et options")

# Localité
locs = sorted(df_cons["Localité"].unique())
sel_loc = st.sidebar.selectbox("Localité", locs)

# Recherche par SN
search_sn = st.sidebar.text_input("Rechercher un compteur (Meter SN)")

# Filtre de montant
min_amt, max_amt = st.sidebar.slider(
    "Plage de Montant (XAF)",
    float(df_rech["Montant"].min()),
    float(df_rech["Montant"].max()),
    (float(df_rech["Montant"].min()), float(df_rech["Montant"].max()))
)

# Filtre de date si applicable
if "Date" in df_rech.columns:
    min_date, max_date = st.sidebar.date_input(
        "Période de recharge",
        [df_rech["Date"].min(), df_rech["Date"].max()]
    )
else:
    min_date = max_date = None

# Autoriser export CSV
export_csv = st.sidebar.checkbox("Autoriser l’export CSV", value=True)

# ---------------- TABS ----------------
tab1, tab2, tab3 = st.tabs(["📈 Aperçu", "🔎 Détails", "🏆 Classement"])

# ---------- TAB 1 : APERÇU ----------
with tab1:
    df_loc = df_cons[df_cons["Localité"] == sel_loc]
    data = pd.merge(df_loc, df_rech, on="Meter SN", how="left")

    # Appliquer filtres
    if search_sn:
        data = data[data["Meter SN"].str.contains(search_sn, na=False)]
    data = data[(data["Montant"] >= min_amt) & (data["Montant"] <= max_amt)]
    if min_date:
        data = data.query("@min_date <= Date <= @max_date") if "Date" in data.columns else data

    # KPIs
    col1, col2 = st.columns(2)
    col1.metric("📌 Compteurs affichés", f"{len(df_loc)}")
    col2.metric("💰 Total Recharges", f"{data['Montant'].sum():,.0f} XAF")

    # Sparkline temporelle si Date présente
    if "Date" in data.columns:
        timeser = data.groupby("Date")["Montant"].sum().reset_index()
        chart = (
            alt.Chart(timeser)
            .mark_line(color="#004080")
            .encode(x="Date", y="Montant")
            .properties(height=100)
        )
        st.altair_chart(chart, use_container_width=True)

    # Histogramme
    st.subheader("Distribution des Montants")
    fig, ax = plt.subplots(figsize=(8, 3))
    sns.histplot(data["Montant"].dropna(), bins=30, kde=True, ax=ax, color="teal")
    ax.set_xlabel("Montant (XAF)")
    ax.set_ylabel("Fréquence")
    st.pyplot(fig)

# ---------- TAB 2 : DÉTAILS ----------
with tab2:
    st.subheader(f"Compteurs & Recharges – {sel_loc}")
    if export_csv:
        csv = data.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Télécharger (CSV)",
            data=csv,
            file_name=f"recharges_{sel_loc}.csv",
            mime="text/csv"
        )
    st.dataframe(data, use_container_width=True, height=400)

    # Carte interactive si disponible
    if FOLIUM_AVAILABLE and {"Latitude", "Longitude"}.issubset(df_cons.columns):
        st.subheader("🗺️ Répartition géographique des compteurs")
        m = folium.Map(
            location=[df_cons["Latitude"].astype(float).mean(), df_cons["Longitude"].astype(float).mean()],
            zoom_start=8
        )
        for _, row in data.iterrows():
            folium.CircleMarker(
                location=(float(row["Latitude"]), float(row["Longitude"])),
                radius=3, color="blue", fill=True
            ).add_to(m)
        st_folium(m, width=700, height=400)
    elif not FOLIUM_AVAILABLE:
        st.warning("🚫 folium non installé : la cartographie est désactivée.")

# ---------- TAB 3 : CLASSEMENT ----------
with tab3:
    df_full = pd.merge(df_cons, df_rech, on="Meter SN", how="left")
    if search_sn:
        df_full = df_full[df_full["Meter SN"].str.contains(search_sn, na=False)]
    df_full = df_full[(df_full["Montant"] >= min_amt) & (df_full["Montant"] <= max_amt)]
    if min_date:
        df_full = df_full.query("@min_date <= Date <= @max_date") if "Date" in df_full.columns else df_full

    classement = (
        df_full.groupby("Localité")["Montant"]
        .sum()
        .reset_index()
        .sort_values("Montant", ascending=False)
        .rename(columns={"Montant": "Total (XAF)"})
    )
    st.subheader("Classement global des localités")
    st.dataframe(classement, use_container_width=True, height=400)

    fig2, ax2 = plt.subplots(figsize=(10, 6))
    sns.barplot(
        data=classement.head(10),
        x="Total (XAF)",
        y="Localité",
        palette="Blues_r",
        ax=ax2
    )
    ax2.set_title("Top 10 localités par Montant total")
    ax2.set_xlabel("Total (XAF)")
    ax2.set_ylabel("")
    st.pyplot(fig2)

time.sleep(2)
# ---------------- FOOTER ----------------
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;font-size:12px;'>© MBOG Aime Thierry 2025 AER • Tableau de bord professionnel • Tous droits réservés</div>",
    unsafe_allow_html=True
)
