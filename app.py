import glob
import io
import os
import unicodedata
import branca.colormap as cm
import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

# Configuração da Página
st.set_page_config(
    page_title="Painel de Arboviroses | Recife",
    page_icon="🦟",
    layout="wide",
)

# Custom CSS: Melhora a usabilidade do botão da barra lateral no Mobile
st.markdown("""
<style>
/* Destaca o botão da sidebar no mobile */
button[kind="header"] {
    background-color: #38BDF8 !important;
    color: #070B14 !important;
    border-radius: 8px !important;
    padding: 4px 10px !important;
    font-weight: bold !important;
}

button[kind="header"]::after {
    content: " ⚙️ Filtros";
    font-size: 0.82rem;
    color: #070B14;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

# 1. Dicionário Oficial de RPAs do Recife
RPAS_RECIFE = {
    "RPA 1 (Centro)": [
        "RECIFE", "SANTO ANTONIO", "SAO JOSE", "ILHA DO LEITE",
        "BOA VISTA", "CABANGA", "COELHOS", "SOLEDADE",
        "ILHA JOANA BEZERRA", "PAISSANDU", "SANTO AMARO",
    ],
    "RPA 2 (Norte)": [
        "ARRUDA", "CAMPINA DO BARRETO", "CAMPO GRANDE", "ENCRUZILHADA",
        "HIPODROMO", "PEIXINHOS", "PONTO DE PARADA", "ROSARINHO",
        "TORREAO", "AGUANAZINHA", "AGUA FRIA", "ALTO SANTA TEREZINHA",
        "BOMBA DO HEMETERIO", "CAJUEIRO", "FUNDAO", "PORTO DA MADEIRA",
        "BEBERIBE", "DOIS UNIDOS", "LINHA DO TIRO",
    ],
    "RPA 3 (Noroeste)": [
        "AFLITOS", "ALTO DO MANDU", "ALTO JOSE DO PINHO", "APIPUCOS",
        "CASA AMARELA", "CASA FORTE", "CORREGO DO JENIPAPO", "DERBY",
        "DOIS IRMAOS", "ESPINHEIRO", "GRACAS", "GUABIRABA", "JAQUEIRA",
        "MACAXEIRA", "MONTEIRO", "NOVA DESCOBERTA", "PARNAMIRIM",
        "PASSARINHO", "POCO DA PANELA", "SANTANA", "SITIO DOS PINTOS",
        "TAMARINEIRA", "VASCO DA GAMA", "BREJO DA GUABIRABA",
        "BREJO DE BEBERIBE", "PAU FERRO", "MANGABEIRA", "ALTO JOSE BONIFACIO",
    ],
    "RPA 4 (Oeste)": [
        "CORDEIRO", "ILHA DO RETIRO", "IPUTINGA", "MADALENA", "PRADO",
        "TORRE", "ZUMBI", "ENGENHO DO MEIO", "TORROES", "VARZEA",
        "CAXANGA", "CIDADE UNIVERSITARIA",
    ],
    "RPA 5 (Sudoeste)": [
        "AFOGADOS", "AREIAS", "BARRO", "BONGI", "CACOTE", "COQUEIRAL",
        "CURADO", "ESTANCIA", "JARDIM SAO PAULO", "JIQUIÁ", "JIQUIA",
        "MANGUEIRA", "MUSTARDINHA", "SAN MARTIN", "SANCHO", "TEJIPIO",
        "TOTÓ", "TOTO",
    ],
    "RPA 6 (Sul)": [
        "BOA VIAGEM", "BRASILIA TEIMOSA", "IMBIRIBEIRA", "IPSEP",
        "PINA", "IBURA", "JORDAO", "COHAB",
    ],
}


def identificar_rpa(bairro_norm):
    for rpa, bairros in RPAS_RECIFE.items():
        if any(b in bairro_norm for b in bairros):
            return rpa
    return "Outros / Indefinido"


def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto_str = str(texto).strip().upper()
    nfkd = unicodedata.normalize("NFKD", texto_str)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def processar_dataframe_bruto(df_raw):
    df_raw.columns = [str(c).lower().strip() for c in df_raw.columns]
    col_combo = [c for c in df_raw.columns if "," in c]

    dfs_para_unir = []

    # 1. Trata registros concatenados por vírgula (34.556 casos de dengue de 2015)
    if col_combo:
        col_c = col_combo[0]
        serie_combo = df_raw[col_c].dropna().astype(str)
        if len(serie_combo) > 0:
            linhas_texto = [col_c] + serie_combo.tolist()
            buffer = io.StringIO("\n".join(linhas_texto))
            try:
                df_sub = pd.read_csv(
                    buffer, sep=",", low_memory=False, on_bad_lines="skip"
                )
                df_sub.columns = [str(c).lower().strip() for c in df_sub.columns]
                dfs_para_unir.append(df_sub)
            except Exception:
                pass

        df_principal = df_raw.drop(columns=[col_c]).dropna(how="all")
        dfs_para_unir.append(df_principal)
    else:
        dfs_para_unir.append(df_raw)

    registros = []
    for d in dfs_para_unir:
        if d.empty:
            continue

        col_b = next(
            (
                c
                for c in [
                    "no_bairro_residencia",
                    "nm_bairro",
                    "bairro",
                    "bairro_norm",
                ]
                if c in d.columns
            ),
            None,
        )
        col_a = next(
            (
                c
                for c in ["co_cid", "id_agravo", "agravo", "tp_notificacao"]
                if c in d.columns
            ),
            None,
        )

        if not col_b:
            continue

        df_c = pd.DataFrame()
        df_c["bairro_norm"] = d[col_b].apply(normalizar_texto)

        # Identificação de Dengue, Chikungunya e Zika
        if col_a and col_a in d.columns:
            s = d[col_a].astype(str).str.upper().str.strip()
            df_c["is_dengue"] = s.str.contains(
                r"^A90|^A91|DENG", regex=True, na=False
            ).astype(int)
            df_c["is_zika"] = s.str.contains(
                r"^A928|^A92\.8|^U06|ZIKA", regex=True, na=False
            ).astype(int)
            df_c["is_chik"] = (
                s.str.contains(r"^A920|^A92\.0|CHIK", regex=True, na=False)
                | (s.str.startswith("A92") & (df_c["is_zika"] == 0))
            ).astype(int)
        elif "is_dengue" in d.columns:
            df_c["is_dengue"] = (
                pd.to_numeric(d["is_dengue"], errors="coerce")
                .fillna(0)
                .astype(int)
            )
            df_c["is_chik"] = (
                pd.to_numeric(d.get("is_chik", 0), errors="coerce")
                .fillna(0)
                .astype(int)
            )
            df_c["is_zika"] = (
                pd.to_numeric(d.get("is_zika", 0), errors="coerce")
                .fillna(0)
                .astype(int)
            )
        else:
            df_c["is_dengue"] = 1
            df_c["is_chik"] = 0
            df_c["is_zika"] = 0

        if "is_dengue" in d.columns:
            df_c["is_dengue"] = np.maximum(
                df_c["is_dengue"],
                pd.to_numeric(d["is_dengue"], errors="coerce")
                .fillna(0)
                .astype(int),
            )

        registros.append(df_c)

    if not registros:
        return pd.DataFrame()

    return pd.concat(registros, ignore_index=True)


@st.cache_data
def carregar_dados_completos():
    mesh_path = "data/raw/recife_bairros_rpa.gpkg"
    if not os.path.exists(mesh_path):
        mesh_path = "../data/raw/recife_bairros_rpa.gpkg"

    gdf_bairros = gpd.read_file(mesh_path)
    col_nome = (
        "name_neighborhood"
        if "name_neighborhood" in gdf_bairros.columns
        else gdf_bairros.columns[1]
    )

    gdf_bairros["bairro_norm"] = gdf_bairros[col_nome].apply(normalizar_texto)
    gdf_bairros["rpa_nome"] = gdf_bairros["bairro_norm"].apply(identificar_rpa)
    gdf_bairros["populacao"] = 15000
    gdf_bairros = gdf_bairros.to_crs(epsg=4326)

    raw_dir = "data/raw" if os.path.exists("data/raw") else "../data/raw"
    arquivos_csv = sorted(glob.glob(os.path.join(raw_dir, "arboviroses_*.csv")))

    lista_processados = []
    for caminho in arquivos_csv:
        nome_arquivo = os.path.basename(caminho)
        ano_digits = "".join(filter(str.isdigit, nome_arquivo))
        if not ano_digits:
            continue
        ano = int(ano_digits)

        try:
            df = pd.read_csv(
                caminho, sep=";", encoding="utf-8", low_memory=False
            )
        except Exception:
            df = pd.read_csv(
                caminho, sep=";", encoding="latin1", low_memory=False
            )

        df_limpo = processar_dataframe_bruto(df)
        if not df_limpo.empty:
            agrupado = (
                df_limpo.groupby("bairro_norm")
                .agg(
                    dengue=("is_dengue", "sum"),
                    chikungunya=("is_chik", "sum"),
                    zika=("is_zika", "sum"),
                    total_casos=("bairro_norm", "count"),
                )
                .reset_index()
            )
            agrupado["ano"] = ano
            lista_processados.append(agrupado)

    df_consolidado = pd.concat(lista_processados, ignore_index=True)
    return gdf_bairros, df_consolidado, col_nome


gdf_bairros, df_consolidado, col_nome_bairro = carregar_dados_completos()

# 2. Barra Lateral de Filtros e Exportação
st.sidebar.header("⚙️ Filtros da Análise")

anos_disponiveis = sorted(df_consolidado["ano"].dropna().unique().astype(int))

anos_selecionados = st.sidebar.multiselect(
    "Selecione o(s) Ano(s):",
    options=anos_disponiveis,
    default=anos_disponiveis,
)

tipo_doenca = st.sidebar.radio(
    "Filtrar Agravo:",
    options=["Todas as Arboviroses", "Dengue", "Chikungunya", "Zika"],
)

modo_visualizacao = st.sidebar.selectbox(
    "Métrica de Mapeamento:",
    options=["Casos Absolutos (Volume)", "Taxa de Incidência (por 10k hab.)"],
)

mapa_colunas = {
    "Todas as Arboviroses": "total_casos",
    "Dengue": "dengue",
    "Chikungunya": "chikungunya",
    "Zika": "zika",
}
col_base = mapa_colunas[tipo_doenca]

# 3. Processamento Dinâmico
if not anos_selecionados:
    st.warning(
        "⚠️ Selecione pelo menos um ano na barra lateral para exibir os dados."
    )
    st.stop()

df_filtrado = df_consolidado[df_consolidado["ano"].isin(anos_selecionados)]

df_agrupado = (
    df_filtrado.groupby("bairro_norm")
    .agg(
        dengue=("dengue", "sum"),
        chikungunya=("chikungunya", "sum"),
        zika=("zika", "sum"),
        total_casos=("total_casos", "sum"),
    )
    .reset_index()
)

gdf_mapa = gdf_bairros.merge(df_agrupado, on="bairro_norm", how="left").fillna(
    0
)
for c in ["dengue", "chikungunya", "zika", "total_casos"]:
    gdf_mapa[c] = gdf_mapa[c].astype(int)

# Cálculo da Taxa de Incidência
gdf_mapa["taxa_incidencia"] = (
    (gdf_mapa[col_base] / gdf_mapa["populacao"]) * 10000
).round(1)

if modo_visualizacao == "Casos Absolutos (Volume)":
    col_metrica = col_base
    label_metrica = "Casos Notificados"
else:
    col_metrica = "taxa_incidencia"
    label_metrica = "Taxa / 10k hab."

# Exportação CSV
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Exportar Dados")
csv_data = df_filtrado.to_csv(index=False, sep=";").encode("utf-8")
st.sidebar.download_button(
    label="Baixar Tabela Filtrada (CSV)",
    data=csv_data,
    file_name="arboviroses_recife_filtrado.csv",
    mime="text/csv",
)

# Créditos e Contato na Barra Lateral
st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Desenvolvimento autoral:**  
    **Luan Lucena**  
    *Graduando em Geografia (Bacharelado) – UFPE*  
    *Membro do Grupo NEXUS (Sociedade & Natureza)*
    
    <div style="margin-top: 14px; margin-bottom: 10px;">
        <a href="https://www.instagram.com/obs.sauderecife" target="_blank" style="text-decoration: none; display: flex; align-items: center; gap: 8px; color: #E1306C; font-weight: 600; font-size: 0.95rem;">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect width="20" height="20" x="2" y="2" rx="5" ry="5"></rect>
                <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
                <line x1="17.5" x2="17.51" y1="6.5" y2="6.5"></line>
            </svg>
            <span style="color: #38BDF8;">@obs.sauderecife</span>
        </a>
    </div>

    <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 8px;">
        💬 <strong>Dúvidas ou feedbacks?</strong><br>
        <a href="mailto:luan.lucena@ufpe.br" style="color: #38BDF8; text-decoration: none;">luan.lucena@ufpe.br</a>
    </div>
    """,
    unsafe_allow_html=True,
)

plotly_config = {
    "displayModeBar": False,
    "editable": False,
    "responsive": True,
    "scrollZoom": False,
}

# 4. Indicadores Principais (KPIs)
st.title("🦟 Painel de Arboviroses | Recife")
anos_txt = (
    f"{min(anos_selecionados)}–{max(anos_selecionados)}"
    if len(anos_selecionados) > 1
    else str(anos_selecionados[0])
)
st.caption(
    f"Período Selecionado: **{anos_txt}** | Agravo: **{tipo_doenca}** |"
    f" Métrica: **{label_metrica}**"
)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric(
    "Total de Casos", f"{gdf_mapa['total_casos'].sum():,}".replace(",", ".")
)
kpi2.metric("Dengue", f"{gdf_mapa['dengue'].sum():,}".replace(",", "."))
kpi3.metric(
    "Chikungunya", f"{gdf_mapa['chikungunya'].sum():,}".replace(",", ".")
)
kpi4.metric("Zika", f"{gdf_mapa['zika'].sum():,}".replace(",", "."))

st.markdown("---")

# 5. Visualização Espacial
col_mapa, col_grafico = st.columns([1.6, 1.0])

with col_mapa:
    st.subheader("Distribuição Espacial")
    val_max = max(float(gdf_mapa[col_metrica].max()), 1.0)

    palette = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
    colormap = cm.LinearColormap(
        colors=palette,
        vmin=0,
        vmax=val_max,
        caption=f"{label_metrica} ({tipo_doenca})",
    )

    m = folium.Map(
        location=[-8.0580, -34.9200], zoom_start=11, tiles="OpenStreetMap"
    )

    css_custom = """
    <style>
    .leaflet-control-attribution svg,
    .leaflet-control-attribution a[href*="leafletjs.com"],
    .leaflet-control-attribution .leaflet-attribution-flag {
        display: none !important;
    }
    </style>
    """
    m.get_root().html.add_child(folium.Element(css_custom))

    tooltip = folium.GeoJsonTooltip(
        fields=[
            col_nome_bairro,
            "rpa_nome",
            "total_casos",
            "dengue",
            "chikungunya",
            "zika",
            "taxa_incidencia",
        ],
        aliases=[
            "Bairro:",
            "RPA:",
            "Total Notificações:",
            "• Dengue:",
            "• Chikungunya:",
            "• Zika:",
            "Taxa (10k hab):",
        ],
        localize=True,
        sticky=False,
        style="""
            background-color: #ffffff; 
            color: #111111; 
            border: 1px solid #333; 
            border-radius: 4px; 
            padding: 8px; 
            font-family: sans-serif; 
            font-size: 12px;
        """,
    )

    folium.GeoJson(
        gdf_mapa,
        style_function=lambda feature, cmap=colormap, col=col_metrica: {
            "fillColor": cmap(feature["properties"][col]),
            "color": "#111111",
            "weight": 1.0,
            "fillOpacity": 0.95,
        },
        tooltip=tooltip,
    ).add_to(m)

    colormap.add_to(m)
    st_folium(m, width="100%", height=500)

with col_grafico:
    st.subheader("Top 10 Bairros")
    df_top = gdf_mapa.sort_values(by=col_metrica, ascending=True).tail(10)
    fig_bar = px.bar(
        df_top,
        x=col_metrica,
        y=col_nome_bairro,
        orientation="h",
        text=col_metrica,
        labels={col_metrica: label_metrica, col_nome_bairro: ""},
        color=col_metrica,
        color_continuous_scale="Reds",
    )
    fig_bar.update_coloraxes(showscale=False)
    fig_bar.update_layout(
        showlegend=False,
        height=500,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title=label_metrica,
        yaxis_title=None,
        dragmode=False,
    )
    fig_bar.update_traces(textposition="inside", insidetextanchor="middle")
    st.plotly_chart(fig_bar, use_container_width=True, config=plotly_config)

# 6. Série Temporal e Casos por RPA
st.markdown("---")
col_tempo, col_rpa = st.columns([1.3, 0.9])

with col_tempo:
    st.subheader(f"📈 Série Temporal ({anos_txt})")
    df_evolucao = (
        df_filtrado.groupby("ano")
        .agg(
            dengue=("dengue", "sum"),
            chikungunya=("chikungunya", "sum"),
            zika=("zika", "sum"),
            total_casos=("total_casos", "sum"),
        )
        .reset_index()
    )

    if len(anos_selecionados) == 1:
        df_ano_unico = pd.DataFrame({
            "Agravo": ["Dengue", "Chikungunya", "Zika"],
            "Casos": [
                int(df_evolucao["dengue"].sum()),
                int(df_evolucao["chikungunya"].sum()),
                int(df_evolucao["zika"].sum()),
            ],
        })
        fig_line = px.bar(
            df_ano_unico,
            x="Agravo",
            y="Casos",
            text="Casos",
            color="Agravo",
            color_discrete_map={
                "Dengue": "#e74c3c",
                "Chikungunya": "#f39c12",
                "Zika": "#3498db",
            },
        )
        fig_line.update_traces(textposition="inside", insidetextanchor="middle")
    else:
        if tipo_doenca == "Todas as Arboviroses":
            df_melted = df_evolucao.melt(
                id_vars=["ano"],
                value_vars=["dengue", "chikungunya", "zika"],
                var_name="Agravo",
                value_name="Casos",
            )
            df_melted["Agravo"] = df_melted["Agravo"].str.capitalize()

            fig_line = px.line(
                df_melted,
                x="ano",
                y="Casos",
                color="Agravo",
                markers=True,
                color_discrete_map={
                    "Dengue": "#e74c3c",
                    "Chikungunya": "#f39c12",
                    "Zika": "#3498db",
                },
                labels={"ano": "Ano", "Casos": "Casos"},
            )
        else:
            fig_line = px.line(
                df_evolucao,
                x="ano",
                y=col_base,
                markers=True,
                color_discrete_sequence=["#e74c3c"],
                labels={"ano": "Ano", col_base: "Casos"},
            )

    fig_line.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(
            tickmode="array",
            tickvals=anos_selecionados if len(anos_selecionados) > 1 else None,
            tickformat="d",
            fixedrange=True,
        ),
        yaxis=dict(fixedrange=True),
        hovermode="x unified",
        dragmode=False,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    st.plotly_chart(fig_line, use_container_width=True, config=plotly_config)

with col_rpa:
    st.subheader(f"🏙️ Casos por RPA ({anos_txt})")
    df_rpa = (
        gdf_mapa.groupby("rpa_nome").agg(casos=(col_base, "sum")).reset_index()
    )
    df_rpa = df_rpa[df_rpa["rpa_nome"].str.startswith("RPA")].sort_values(
        by="casos", ascending=False
    )

    fig_rpa = px.bar(
        df_rpa,
        x="rpa_nome",
        y="casos",
        text="casos",
        labels={"rpa_nome": "", "casos": "Casos"},
        color="casos",
        color_continuous_scale="Oranges",
    )
    fig_rpa.update_coloraxes(showscale=False)
    fig_rpa.update_layout(
        showlegend=False,
        height=350,
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True),
        xaxis_title=None,
        yaxis_title="Casos",
        dragmode=False,
    )
    fig_rpa.update_traces(textposition="inside", insidetextanchor="middle")
    st.plotly_chart(fig_rpa, use_container_width=True, config=plotly_config)

# 7. Rodapé
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #888888; font-size: 13px; line-height: 1.6; padding-bottom: 20px;'>
        <b>Painel de Análise Espaço-Temporal de Arboviroses (Recife - PE)</b><br>
        Desenvolvimento autoral: <b>Luan Lucena</b> | Graduando em Geografia (Bacharelado) pela <b>Universidade Federal de Pernambuco (UFPE)</b> | Membro do <b>Grupo NEXUS (Sociedade & Natureza)</b><br>
        Fonte dos dados: Portal de Dados Abertos da Prefeitura do Recife (Sinan / PCR)<br>
        <span style="color: #38BDF8;">Dúvidas, sugestões ou feedbacks?</span> Entre em contato: <a href="mailto:luan.lucena@ufpe.br" style="color: #38BDF8; text-decoration: underline;">luan.lucena@ufpe.br</a>
    </div>
    """,
    unsafe_allow_html=True,
)