import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
import branca.colormap as cm
from streamlit_folium import st_folium
import plotly.express as px
import unicodedata
import glob
import os

# Configuração da Página
st.set_page_config(
    page_title="Painel de Arboviroses | Recife",
    page_icon="🦟",
    layout="wide"
)

# 1. Dicionário Oficial de RPAs do Recife
RPAS_RECIFE = {
    "RPA 1 (Centro)": [
        "RECIFE", "SANTO ANTONIO", "SAO JOSE", "ILHA DO LEITE", "BOA VISTA", 
        "CABANGA", "COELHOS", "SOLEDADE", "ILHA JOANA BEZERRA", "PAISSANDU", "SANTO AMARO"
    ],
    "RPA 2 (Norte)": [
        "ARRUDA", "CAMPINA DO BARRETO", "CAMPO GRANDE", "ENCRUZILHADA", "HIPODROMO", 
        "PEIXINHOS", "PONTO DE PARADA", "ROSARINHO", "TORREAO", "AGUANAZINHA", 
        "AGUA FRIA", "ALTO SANTA TEREZINHA", "BOMBA DO HEMETERIO", "CAJUEIRO", 
        "FUNDAO", "PORTO DA MADEIRA", "BEBERIBE", "DOIS UNIDOS", "LINHA DO TIRO"
    ],
    "RPA 3 (Noroeste)": [
        "AFLITOS", "ALTO DO MANDU", "ALTO JOSE DO PINHO", "APIPUCOS", "CASA AMARELA", 
        "CASA FORTE", "CORREGO DO JENIPAPO", "DERBY", "DOIS IRMAOS", "ESPINHEIRO", 
        "GRACAS", "GUABIRABA", "JAQUEIRA", "MACAXEIRA", "MONTEIRO", "NOVA DESCOBERTA", 
        "PARNAMIRIM", "PASSARINHO", "POCO DA PANELA", "SANTANA", "SITIO DOS PINTOS", 
        "TAMARINEIRA", "VASCO DA GAMA", "BREJO DA GUABIRABA", "BREJO DE BEBERIBE", 
        "PAU FERRO", "MANGABEIRA", "ALTO JOSE BONIFACIO"
    ],
    "RPA 4 (Oeste)": [
        "CORDEIRO", "ILHA DO RETIRO", "IPUTINGA", "MADALENA", "PRADO", 
        "TORRE", "ZUMBI", "ENGENHO DO MEIO", "TORROES", "VARZEA", 
        "CAXANGA", "CIDADE UNIVERSITARIA"
    ],
    "RPA 5 (Sudoeste)": [
        "AFOGADOS", "AREIAS", "BARRO", "BONGI", "CACOTE", "COQUEIRAL", 
        "CURADO", "ESTANCIA", "JARDIM SAO PAULO", "JIQUIÁ", "JIQUIA", "MANGUEIRA", 
        "MUSTARDINHA", "SAN MARTIN", "SANCHO", "TEJIPIO", "TOTÓ", "TOTO"
    ],
    "RPA 6 (Sul)": [
        "BOA VIAGEM", "BRASILIA TEIMOSA", "IMBIRIBEIRA", "IPSEP", "PINA", 
        "IBURA", "JORDAO", "COHAB"
    ]
}

def identificar_rpa(bairro_norm):
    for rpa, bairros in RPAS_RECIFE.items():
        if any(b in bairro_norm for b in bairros) or any(bairros_item in bairro_norm for bairros_item in bairros):
            return rpa
    return "Outros / Indefinido"

def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto_str = str(texto).strip().upper()
    nfkd = unicodedata.normalize("NFKD", texto_str)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])

@st.cache_data
def carregar_dados_completos():
    mesh_path = "data/raw/recife_bairros_rpa.gpkg"
    if not os.path.exists(mesh_path):
        mesh_path = "../data/raw/recife_bairros_rpa.gpkg"
        
    gdf_bairros = gpd.read_file(mesh_path)
    col_nome = "name_neighborhood" if "name_neighborhood" in gdf_bairros.columns else gdf_bairros.columns[1]
    
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
            df = pd.read_csv(caminho, sep=";", encoding="utf-8", low_memory=False)
        except:
            df = pd.read_csv(caminho, sep=";", encoding="latin1", low_memory=False)
            
        df.columns = [c.lower().strip() for c in df.columns]
        
        col_bairro = next((c for c in ["no_bairro_residencia", "nm_bairro", "bairro"] if c in df.columns), None)
        col_agravo = next((c for c in ["co_cid", "id_agravo", "agravo", "tp_notificacao"] if c in df.columns), None)
        
        if col_bairro:
            df_clean = pd.DataFrame()
            df_clean["bairro_norm"] = df[col_bairro].apply(normalizar_texto)
            
            if "is_dengue" in df.columns and "is_chik" in df.columns and "is_zika" in df.columns:
                df_clean["is_dengue"] = df["is_dengue"].fillna(0).astype(int)
                df_clean["is_chik"] = df["is_chik"].fillna(0).astype(int)
                df_clean["is_zika"] = df["is_zika"].fillna(0).astype(int)
            elif col_agravo:
                s = df[col_agravo].astype(str).str.upper().str.strip()
                df_clean["is_dengue"] = s.str.contains(r"^A90|^A91|DENG", regex=True, na=False).astype(int)
                df_clean["is_zika"] = s.str.contains(r"^A928|^A92\.8|^U06|ZIKA", regex=True, na=False).astype(int)
                df_clean["is_chik"] = (s.str.contains(r"^A920|^A92\.0|CHIK", regex=True, na=False) | 
                                       (s.str.startswith("A92") & (df_clean["is_zika"] == 0))).astype(int)
            else:
                df_clean["is_dengue"] = 1
                df_clean["is_chik"] = 0
                df_clean["is_zika"] = 0
                
            agrupado = df_clean.groupby("bairro_norm").agg(
                dengue=("is_dengue", "sum"),
                chikungunya=("is_chik", "sum"),
                zika=("is_zika", "sum"),
                total_casos=("bairro_norm", "count")
            ).reset_index()
            
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
    default=anos_disponiveis
)

tipo_doenca = st.sidebar.radio(
    "Filtrar Agravo:",
    options=["Todas as Arboviroses", "Dengue", "Chikungunya", "Zika"]
)

modo_visualizacao = st.sidebar.selectbox(
    "Métrica de Mapeamento:",
    options=["Casos Absolutos (Volume)", "Taxa de Incidência (por 10k hab.)"]
)

mapa_colunas = {
    "Todas as Arboviroses": "total_casos",
    "Dengue": "dengue",
    "Chikungunya": "chikungunya",
    "Zika": "zika"
}
col_base = mapa_colunas[tipo_doenca]

# 3. Processamento Dinâmico
if not anos_selecionados:
    st.warning("⚠️ Selecione pelo menos um ano na barra lateral para exibir os dados.")
    st.stop()

df_filtrado = df_consolidado[df_consolidado["ano"].isin(anos_selecionados)]

df_agrupado = df_filtrado.groupby("bairro_norm").agg(
    dengue=("dengue", "sum"),
    chikungunya=("chikungunya", "sum"),
    zika=("zika", "sum"),
    total_casos=("total_casos", "sum")
).reset_index()

gdf_mapa = gdf_bairros.merge(df_agrupado, on="bairro_norm", how="left").fillna(0)
for c in ["dengue", "chikungunya", "zika", "total_casos"]:
    gdf_mapa[c] = gdf_mapa[c].astype(int)

# Taxa de Incidência
gdf_mapa["taxa_incidencia"] = ((gdf_mapa[col_base] / gdf_mapa["populacao"]) * 10000).round(1)

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
    mime="text/csv"
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Desenvolvimento:**  
    **Luan Lucena**  
    *Graduando em Geografia (Bacharelado)*  
    *Universidade Federal de Pernambuco (UFPE)*  
    *Grupo NEXUS – Sociedade & Natureza*
    """
)

# Configuração responsiva e desativação do drag zoom em dispositivos touch
plotly_config = {
    "displayModeBar": False,
    "staticPlot": False,
    "responsive": True,
    "scrollZoom": False
}

# 4. Indicadores Principais (KPIs)
st.title("🦟 Monitoramento Espaço-Temporal de Arboviroses em Recife")
st.caption(f"Período selecionado: **{', '.join(map(str, sorted(anos_selecionados)))}** | Filtro: **{tipo_doenca}** | Métrica: **{label_metrica}**")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total de Casos", f"{gdf_mapa['total_casos'].sum():,}".replace(",", "."))
kpi2.metric("Dengue", f"{gdf_mapa['dengue'].sum():,}".replace(",", "."))
kpi3.metric("Chikungunya", f"{gdf_mapa['chikungunya'].sum():,}".replace(",", "."))
kpi4.metric("Zika", f"{gdf_mapa['zika'].sum():,}".replace(",", "."))

st.markdown("---")

# 5. Visualização: Mapa Ampliado e Top Bairros
col_mapa, col_grafico = st.columns([1.8, 1.0])

with col_mapa:
    st.subheader(f"Distribuição Espacial ({label_metrica})")
    val_max = max(float(gdf_mapa[col_metrica].max()), 1.0)
    
    palette = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
    colormap = cm.LinearColormap(colors=palette, vmin=0, vmax=val_max, caption=f"{label_metrica} ({tipo_doenca})")
    
    m = folium.Map(
        location=[-8.0580, -34.9200], 
        zoom_start=12, 
        tiles="OpenStreetMap"
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
        fields=[col_nome_bairro, "rpa_nome", "total_casos", "dengue", "chikungunya", "zika", "taxa_incidencia"],
        aliases=["Bairro:", "RPA:", "Total Notificações:", "• Dengue:", "• Chikungunya:", "• Zika:", "Taxa (10k hab):"],
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
        """
    )
    
    folium.GeoJson(
        gdf_mapa,
        style_function=lambda feature, cmap=colormap, col=col_metrica: {
            "fillColor": cmap(feature["properties"][col]),
            "color": "#111111",
            "weight": 1.0,
            "fillOpacity": 0.95,
        },
        tooltip=tooltip
    ).add_to(m)
    
    colormap.add_to(m)
    st_folium(m, width="100%", height=550)

with col_grafico:
    st.subheader(f"Top 10 Bairros ({label_metrica})")
    df_top = gdf_mapa.sort_values(by=col_metrica, ascending=True).tail(10)
    fig_bar = px.bar(
        df_top,
        x=col_metrica,
        y=col_nome_bairro,
        orientation="h",
        text=col_metrica,
        labels={col_metrica: label_metrica, col_nome_bairro: "Bairro"},
        color=col_metrica,
        color_continuous_scale="Reds"
    )
    fig_bar.update_layout(
        showlegend=False,
        height=550,
        margin=dict(l=0, r=20, t=30, b=0),
        xaxis_title=label_metrica,
        yaxis_title=None,
        dragmode=False
    )
    st.plotly_chart(fig_bar, use_container_width=True, config=plotly_config)

# 6. Análise por RPA e Série Temporal Histórica
st.markdown("---")
col_tempo, col_rpa = st.columns([1.3, 0.9])

with col_tempo:
    st.subheader("📈 Evolução Temporal (2015–2024)")
    df_evolucao = df_consolidado.groupby("ano").agg(
        dengue=("dengue", "sum"),
        chikungunya=("chikungunya", "sum"),
        zika=("zika", "sum"),
        total_casos=("total_casos", "sum")
    ).reset_index()

    if tipo_doenca == "Todas as Arboviroses":
        df_melted = df_evolucao.melt(
            id_vars=["ano"], 
            value_vars=["dengue", "chikungunya", "zika"],
            var_name="Agravo", 
            value_name="Casos"
        )
        df_melted["Agravo"] = df_melted["Agravo"].str.capitalize()
        
        fig_line = px.line(
            df_melted,
            x="ano",
            y="Casos",
            color="Agravo",
            markers=True,
            color_discrete_map={"Dengue": "#e74c3c", "Chikungunya": "#f39c12", "Zika": "#3498db"},
            labels={"ano": "Ano", "Casos": "Notificações"}
        )
    else:
        fig_line = px.line(
            df_evolucao,
            x="ano",
            y=col_base,
            markers=True,
            color_discrete_sequence=["#e74c3c"],
            labels={"ano": "Ano", col_base: f"Casos de {tipo_doenca}"}
        )

    fig_line.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(tickmode="linear", tick0=2015, dtick=1),
        hovermode="x unified",
        dragmode=False
    )
    st.plotly_chart(fig_line, use_container_width=True, config=plotly_config)

with col_rpa:
    st.subheader("🏙️ Casos por RPA")
    df_rpa = gdf_mapa.groupby("rpa_nome").agg(casos=(col_base, "sum")).reset_index()
    df_rpa = df_rpa[df_rpa["rpa_nome"].str.startswith("RPA")].sort_values(by="casos", ascending=False)
    
    fig_rpa = px.bar(
        df_rpa,
        x="rpa_nome",
        y="casos",
        text="casos",
        labels={"rpa_nome": "Região Sanitária / RPA", "casos": "Casos"},
        color="casos",
        color_continuous_scale="Oranges"
    )
    fig_rpa.update_layout(
        showlegend=False,
        height=360,
        margin=dict(l=10, r=10, t=30, b=20),
        xaxis_title=None,
        yaxis_title="Notificações",
        dragmode=False
    )
    st.plotly_chart(fig_rpa, use_container_width=True, config=plotly_config)

# 7. Rodapé
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #888888; font-size: 13px; line-height: 1.6;'>
        <b>Painel de Análise Espaço-Temporal de Arboviroses (Recife - PE)</b><br>
        Desenvolvimento: <b>Luan Lucena</b> | Graduando em Geografia (Bacharelado) pela <b>Universidade Federal de Pernambuco (UFPE)</b> | <b>Grupo NEXUS (Sociedade & Natureza)</b><br>
        Fonte dos dados: Portal de Dados Abertos da Prefeitura do Recife (Sinan / PCR)
    </div>
    """,
    unsafe_allow_html=True
)