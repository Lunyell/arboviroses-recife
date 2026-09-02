cat << 'EOF' > app.py
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

st.set_page_config(
    page_title="Painel Epidemiológico | Recife",
    page_icon="🦟",
    layout="wide",
)

st.markdown("""
<style>
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="stSidebarCollapseButton"] button {
    background-color: #38BDF8 !important;
    color: #070B14 !important;
    border-radius: 8px !important;
    padding: 4px 10px !important;
    font-weight: bold !important;
}
[data-testid="stSidebarCollapsedControl"] button::after {
    content: " Filtros";
    font-size: 0.82rem;
    color: #070B14;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

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
    if col_combo:
        col_c = col_combo[0]
        serie_combo = df_raw[col_c].dropna().astype(str)
        if len(serie_combo) > 0:
            linhas_texto = [col_c] + serie_combo.tolist()
            buffer = io.StringIO("\n".join(linhas_texto))
            try:
                df_sub = pd.read_csv(buffer, sep=",", low_memory=False, on_bad_lines="skip")
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
        col_b = next((c for c in ["no_bairro_residencia", "nm_bairro", "bairro", "bairro_norm"] if c in d.columns), None)
        col_a = next((c for c in ["co_cid", "id_agravo", "agravo", "tp_notificacao"] if c in d.columns), None)
        if not col_b:
            continue

        df_c = pd.DataFrame()
        df_c["bairro_norm"] = d[col_b].apply(normalizar_texto)

        if col_a and col_a in d.columns:
            s = d[col_a].astype(str).str.upper().str.strip()
            df_c["is_dengue"] = s.str.contains(r"^A90|^A91|DENG", regex=True, na=False).astype(int)
            df_c["is_zika"] = s.str.contains(r"^A928|^A92\.8|^U06|ZIKA", regex=True, na=False).astype(int)
            df_c["is_chik"] = (s.str.contains(r"^A920|^A92\.0|CHIK", regex=True, na=False) | (s.str.startswith("A92") & (df_c["is_zika"] == 0))).astype(int)
        elif "is_dengue" in d.columns:
            df_c["is_dengue"] = pd.to_numeric(d["is_dengue"], errors="coerce").fillna(0).astype(int)
            df_c["is_chik"] = pd.to_numeric(d.get("is_chik", 0), errors="coerce").fillna(0).astype(int)
            df_c["is_zika"] = pd.to_numeric(d.get("is_zika", 0), errors="coerce").fillna(0).astype(int)
        elif "dengue" in d.columns:
            df_c["is_dengue"] = pd.to_numeric(d["dengue"], errors="coerce").fillna(0).astype(int)
            df_c["is_chik"] = pd.to_numeric(d.get("chikungunya", 0), errors="coerce").fillna(0).astype(int)
            df_c["is_zika"] = pd.to_numeric(d.get("zika", 0), errors="coerce").fillna(0).astype(int)
        else:
            df_c["is_dengue"] = 1
            df_c["is_chik"] = 0
            df_c["is_zika"] = 0

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
        except Exception:
            df = pd.read_csv(caminho, sep=";", encoding="latin1", low_memory=False)

        df_limpo = processar_dataframe_bruto(df)
        if not df_limpo.empty:
            c_dengue = "is_dengue" if "is_dengue" in df_limpo.columns else ("dengue" if "dengue" in df_limpo.columns else None)
            c_chik = "is_chik" if "is_chik" in df_limpo.columns else ("chikungunya" if "chikungunya" in df_limpo.columns else None)
            c_zika = "is_zika" if "is_zika" in df_limpo.columns else ("zika" if "zika" in df_limpo.columns else None)

            if c_dengue is None: df_limpo["is_dengue"] = 0; c_dengue = "is_dengue"
            if c_chik is None: df_limpo["is_chik"] = 0; c_chik = "is_chik"
            if c_zika is None: df_limpo["is_zika"] = 0; c_zika = "is_zika"

            agrupado = df_limpo.groupby("bairro_norm").agg(
                dengue=(c_dengue, "sum"),
                chikungunya=(c_chik, "sum"),
                zika=(c_zika, "sum"),
                total_casos=("bairro_norm", "count"),
            ).reset_index()
            agrupado["ano"] = ano
            lista_processados.append(agrupado)

    df_consolidado = pd.concat(lista_processados, ignore_index=True)
    return gdf_bairros, df_consolidado, col_nome

@st.cache_data
def carregar_dados_leptospirose():
    path_mensal = "data/processed/leptospirose_recife_mensal.csv"
    if not os.path.exists(path_mensal):
        path_mensal = "../data/processed/leptospirose_recife_mensal.csv"

    df_mensal = pd.DataFrame()
    if os.path.exists(path_mensal):
        df_mensal = pd.read_csv(path_mensal, sep=";")
        df_mensal = df_mensal[df_mensal["ano"] >= 2007].sort_values("ano").reset_index(drop=True)

    path_bairros = "data/processed/leptospirose_bairros_risco.csv"
    if not os.path.exists(path_bairros):
        path_bairros = "../data/processed/leptospirose_bairros_risco.csv"
    
    df_bairros = pd.DataFrame()
    if os.path.exists(path_bairros):
        df_bairros = pd.read_csv(path_bairros, sep=";")

    path_ds = "data/processed/leptospirose_distritos_consolidado.csv"
    if not os.path.exists(path_ds):
        path_ds = "../data/processed/leptospirose_distritos_consolidado.csv"
    
    df_ds = pd.DataFrame()
    if os.path.exists(path_ds):
        df_ds = pd.read_csv(path_ds, sep=";")

    return df_mensal, df_bairros, df_ds

gdf_bairros, df_consolidado, col_nome_bairro = carregar_dados_completos()
df_lepto_mensal, df_lepto_bairros, df_lepto_ds = carregar_dados_leptospirose()

plotly_config = {
    "displayModeBar": False,
    "editable": False,
    "responsive": True,
    "scrollZoom": False,
}

opcoes_modulo = ["🦟 Arboviroses (Dengue, Chik, Zika)", "🐀 Leptospirose (Série SINAN)"]
modulo_ativo = st.radio(
    "Selecione o Painel Epidemiológico:",
    options=opcoes_modulo,
    horizontal=True,
    label_visibility="collapsed",
)

st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

# ==============================================================================
# 1. VISÃO: ARBOVIROSES
# ==============================================================================
if modulo_ativo == "🦟 Arboviroses (Dengue, Chik, Zika)":
    st.sidebar.header("⚙️ Filtros de Arboviroses")

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

    if not anos_selecionados:
        st.warning("⚠️ Selecione pelo menos um ano na barra lateral para exibir os dados de Arboviroses.")
        st.stop()

    df_filtrado = df_consolidado[df_consolidado["ano"].isin(anos_selecionados)]
    df_agrupado = df_filtrado.groupby("bairro_norm").agg(
        dengue=("dengue", "sum"),
        chikungunya=("chikungunya", "sum"),
        zika=("zika", "sum"),
        total_casos=("total_casos", "sum"),
    ).reset_index()

    gdf_mapa = gdf_bairros.merge(df_agrupado, on="bairro_norm", how="left").fillna(0)
    for c in ["dengue", "chikungunya", "zika", "total_casos"]:
        gdf_mapa[c] = gdf_mapa[c].astype(int)

    gdf_mapa["taxa_incidencia"] = ((gdf_mapa[col_base] / gdf_mapa["populacao"]) * 10000).round(1)

    if modo_visualizacao == "Casos Absolutos (Volume)":
        col_metrica = col_base
        label_metrica = "Casos Notificados"
    else:
        col_metrica = "taxa_incidencia"
        label_metrica = "Taxa / 10k hab."

    st.sidebar.markdown("---")
    st.sidebar.subheader("📥 Exportar Dados")
    csv_data = df_filtrado.to_csv(index=False, sep=";").encode("utf-8")
    st.sidebar.download_button(
        label="Baixar Tabela de Arboviroses (CSV)",
        data=csv_data,
        file_name="arboviroses_recife_filtrado.csv",
        mime="text/csv",
    )

    st.title("🦟 Painel de Arboviroses | Recife")
    anos_txt = f"{min(anos_selecionados)}–{max(anos_selecionados)}" if len(anos_selecionados) > 1 else str(anos_selecionados[0])
    st.caption(f"Período Selecionado: **{anos_txt}** | Agravo: **{tipo_doenca}** | Métrica: **{label_metrica}**")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total de Casos", f"{gdf_mapa['total_casos'].sum():,}".replace(",", "."))
    kpi2.metric("Dengue", f"{gdf_mapa['dengue'].sum():,}".replace(",", "."))
    kpi3.metric("Chikungunya", f"{gdf_mapa['chikungunya'].sum():,}".replace(",", "."))
    kpi4.metric("Zika", f"{gdf_mapa['zika'].sum():,}".replace(",", "."))

    st.markdown("---")

    with st.expander("ℹ️ Entenda as Arboviroses e por que o mapeamento no Recife é essencial", expanded=False):
        st.markdown("""
        ### 🦟 O que são Arboviroses e como elas afetam a nossa saúde?
        O termo **arbovirose** vem da junção em inglês de *arthropod-borne virus* (vírus transmitidos por artrópodes). No ambiente urbano do Recife, essas doenças são transmitidas principalmente pela picada da fêmea do mosquito **_Aedes aegypti_**. As três principais que afetam nossa cidade são:

        * **Dengue:** Provoca febre alta e repentina, dor de cabeça muito forte, dor atrás dos olhos e dores musculares intensas (sensação de "corpo quebrado"). Em casos graves, a dengue pode causar sangramentos, queda brusca de pressão e levar à internação em UTI. Como existem 4 sorotipos diferentes do vírus, uma pessoa pode ter dengue até quatro vezes, sendo que as reinfecções costumam ter risco aumentado de gravidade.
        * **Chikungunya:** É conhecida pelas dores articulares (nas "juntas") extremamente intensas e debilitantes. A pessoa muitas vezes mal consegue caminhar ou segurar objetos. O grande desafio da Chikungunya é que, mesmo depois que a febre passa, as dores nas articulações podem se tornar crônicas e durar meses ou até anos, prejudicando gravemente a rotina de trabalho e a qualidade de vida.
        * **Zika:** Geralmente causa sintomas mais leves no momento da infecção, como manchas vermelhas na pele que coçam muito (exantema), olhos vermelhos e febre baixa. No entanto, o Zika trouxe um impacto histórico mundial para o Recife: a infecção em mulheres grávidas pode provocar a **Síndrome da Zika Congênita** (com casos de microcefalia nos bebês), além de estar associada a complicações neurológicas como a Síndrome de Guillain-Barré.

        ---

        ### 🏙️ Por que o mosquito se espalha mais em certos bairros?
        O mosquito não escolhe bairros por acaso. A proliferação das arboviroses está diretamente ligada à **estrutura e organização do espaço urbano**:

        1. **Acesso à Água e Saneamento:** Em áreas onde o abastecimento de água é irregular ou intermitente, os moradores precisam guardar água em baldes, tonéis e caixas d'água. Se esses recipientes não ficarem perfeitamente vedados, tornam-se criadouros ideais para o mosquito.
        2. **Drenagem e Lixo:** Bairros com deficiência na coleta regular de lixo ou com canais e galerias pluviais assoreadas acumulam água parada com muito mais facilidade, especialmente no período de chuvas.
        3. **Clima e Temperatura:** Recife é uma cidade quente e úmida. O calor acelera o ciclo de vida do mosquito: os ovos eclodem e viram adultos muito mais rápido, aumentando a velocidade de circulação dos vírus.

        ---

        ### 🗺️ Por que mapear os dados bairro a bairro é tão importante?
        Olhar apenas para o número total de casos de toda a cidade esconde a realidade de cada comunidade. Mapear os dados no nível de bairros e RPAs (Regiões Político-Administrativas) faz toda a diferença porque:

        * **Mostra onde agir primeiro:** Permite que a vigilância em saúde saiba exatamente quais bairros estão virando focos (*hotspots*) de transmissão antes que a doença se espalhe para a cidade inteira.
        * **Direciona os recursos públicos:** Facilita o envio de agentes de endemias, aplicação de larvicidas e mutirões de limpeza para os locais mais críticos, otimizando o dinheiro público e salvando vidas.
        * **Informa a população:** Quando você sabe que o seu bairro ou a sua região está com muitos casos registrados, os cuidados individuais e comunitários aumentam naturalmente.
        * **Democratiza a informação:** Transforma dados brutos e complexos em gráficos e mapas simples de entender, aproximando a pesquisa científica da sociedade e fortalecendo o controle social.
        """)

    st.markdown("---")

    col_mapa, col_grafico = st.columns([1.6, 1.0])

    with col_mapa:
        st.subheader("Distribuição Espacial")
        st.caption("💡 **Para que serve:** Espacializa os focos de transmissão na malha urbana. Passe o cursor sobre o bairro para inspecionar notificações e taxas.")
        val_max = max(float(gdf_mapa[col_metrica].max()), 1.0)
        palette = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
        colormap = cm.LinearColormap(colors=palette, vmin=0, vmax=val_max, caption=f"{label_metrica} ({tipo_doenca})")

        m = folium.Map(location=[-8.0580, -34.9200], zoom_start=11, tiles="OpenStreetMap")
        m.get_root().html.add_child(folium.Element("""
            <style>
            .leaflet-control-attribution svg, .leaflet-control-attribution a[href*="leafletjs.com"], .leaflet-control-attribution .leaflet-attribution-flag { display: none !important; }
            </style>
        """))

        tooltip = folium.GeoJsonTooltip(
            fields=[col_nome_bairro, "rpa_nome", "total_casos", "dengue", "chikungunya", "zika", "taxa_incidencia"],
            aliases=["Bairro:", "RPA:", "Total Notificações:", "• Dengue:", "• Chikungunya:", "• Zika:", "Taxa (10k hab):"],
            localize=True,
            style="background-color: #ffffff; color: #111111; border: 1px solid #333; border-radius: 4px; padding: 8px; font-family: sans-serif; font-size: 12px;"
        )

        folium.GeoJson(
            gdf_mapa,
            style_function=lambda feature, cmap=colormap, col=col_metrica: {
                "fillColor": cmap(feature["properties"][col]), "color": "#111111", "weight": 1.0, "fillOpacity": 0.95,
            },
            tooltip=tooltip,
        ).add_to(m)

        colormap.add_to(m)
        st_folium(m, width="100%", height=500)

    with col_grafico:
        st.subheader("Top 10 Bairros")
        st.caption("💡 **Para que serve:** Ranqueia as localidades com maior carga da doença, auxiliando na triagem e envio emergencial de equipes de campo.")
        df_top = gdf_mapa.sort_values(by=col_metrica, ascending=True).tail(10)
        fig_bar = px.bar(
            df_top, x=col_metrica, y=col_nome_bairro, orientation="h", text=col_metrica,
            labels={col_metrica: label_metrica, col_nome_bairro: ""},
            color=col_metrica, color_continuous_scale="Reds",
        )
        fig_bar.update_coloraxes(showscale=False)
        fig_bar.update_layout(showlegend=False, height=500, margin=dict(l=10, r=10, t=10, b=10), dragmode=False)
        fig_bar.update_traces(textposition="inside", insidetextanchor="middle")
        st.plotly_chart(fig_bar, use_container_width=True, config=plotly_config)

    st.markdown("---")
    col_tempo, col_rpa = st.columns([1.3, 0.9])

    with col_tempo:
        st.subheader(f"📈 Série Temporal ({anos_txt})")
        st.caption("💡 **Para que serve:** Monitora a evolução histórica das ondas epidêmicas ao longo dos anos, diferenciando a dinâmica de cada vírus.")
        df_evolucao = df_filtrado.groupby("ano").agg(
            dengue=("dengue", "sum"),
            chikungunya=("chikungunya", "sum"),
            zika=("zika", "sum"),
            total_casos=("total_casos", "sum"),
        ).reset_index()

        if len(anos_selecionados) == 1:
            df_ano_unico = pd.DataFrame({
                "Agravo": ["Dengue", "Chikungunya", "Zika"],
                "Casos": [int(df_evolucao["dengue"].sum()), int(df_evolucao["chikungunya"].sum()), int(df_evolucao["zika"].sum())],
            })
            fig_line = px.bar(df_ano_unico, x="Agravo", y="Casos", text="Casos", color="Agravo",
                              color_discrete_map={"Dengue": "#e74c3c", "Chikungunya": "#f39c12", "Zika": "#3498db"})
            fig_line.update_traces(textposition="inside", insidetextanchor="middle")
        else:
            if tipo_doenca == "Todas as Arboviroses":
                df_melted = df_evolucao.melt(id_vars=["ano"], value_vars=["dengue", "chikungunya", "zika"], var_name="Agravo", value_name="Casos")
                df_melted["Agravo"] = df_melted["Agravo"].str.capitalize()
                fig_line = px.line(df_melted, x="ano", y="Casos", color="Agravo", markers=True,
                                   color_discrete_map={"Dengue": "#e74c3c", "Chikungunya": "#f39c12", "Zika": "#3498db"})
            else:
                fig_line = px.line(df_evolucao, x="ano", y=col_base, markers=True, color_discrete_sequence=["#e74c3c"])

        fig_line.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10), dragmode=False)
        st.plotly_chart(fig_line, use_container_width=True, config=plotly_config)

    with col_rpa:
        st.subheader(f"🏙️ Casos por RPA ({anos_txt})")
        st.caption("💡 **Para que serve:** Agrupa a incidência nas macrodivisões do município, evidenciando contrastes territoriais e de infraestrutura.")
        df_rpa = gdf_mapa.groupby("rpa_nome").agg(casos=(col_base, "sum")).reset_index()
        df_rpa = df_rpa[df_rpa["rpa_nome"].str.startswith("RPA")].sort_values(by="casos", ascending=False)
        fig_rpa = px.bar(df_rpa, x="rpa_nome", y="casos", text="casos", color="casos", color_continuous_scale="Oranges")
        fig_rpa.update_coloraxes(showscale=False)
        fig_rpa.update_layout(showlegend=False, height=350, margin=dict(l=10, r=10, t=20, b=10), dragmode=False)
        fig_rpa.update_traces(textposition="inside", insidetextanchor="middle")
        st.plotly_chart(fig_rpa, use_container_width=True, config=plotly_config)

# ==============================================================================
# 2. VISÃO: LEPTOSPIROSE
# ==============================================================================
else:
    st.sidebar.header("⚙️ Filtros de Leptospirose")

    if not df_lepto_mensal.empty:
        anos_lep_disp = sorted(df_lepto_mensal["ano"].unique().astype(int))

        anos_lep_sel = st.sidebar.multiselect(
            "Selecione o(s) Ano(s):",
            options=anos_lep_disp,
            default=anos_lep_disp,
        )

        if not anos_lep_sel:
            st.warning("⚠️ Selecione pelo menos um ano na barra lateral para exibir os dados de Leptospirose.")
            st.stop()

        todos_distritos = sorted(df_lepto_ds["distrito"].dropna().unique().tolist()) if not df_lepto_ds.empty else []
        distritos_selecionados = st.sidebar.multiselect(
            "Filtrar Distrito Sanitário:",
            options=todos_distritos,
            default=todos_distritos,
        )

        modo_mapa_lepto = st.sidebar.selectbox(
            "Métrica de Mapeamento:",
            options=["Taxa de Incidência (por 100k hab)", "Casos Estimados (Volume)"],
        )

        df_lep_view = df_lepto_mensal[df_lepto_mensal["ano"].isin(anos_lep_sel)].copy()

        st.sidebar.markdown("---")
        st.sidebar.subheader("📥 Exportar Dados")
        csv_lep = df_lep_view.to_csv(index=False, sep=";").encode("utf-8")
        st.sidebar.download_button(
            label="Baixar Tabela de Leptospirose (CSV)",
            data=csv_lep,
            file_name="leptospirose_recife_filtrado.csv",
            mime="text/csv",
        )
    else:
        df_lep_view = pd.DataFrame()
        distritos_selecionados = []

    st.title("🐀 Vigilância Epidemiológica: Leptospirose | Recife")

    if df_lep_view.empty:
        st.warning("⚠️ Execute `python src/python/06_process_leptospirose_distritos.py` para gerar a base de risco.")
    else:
        anos_lep_txt = f"{min(anos_lep_sel)}–{max(anos_lep_sel)}" if len(anos_lep_sel) > 1 else str(anos_lep_sel[0])
        st.caption(f"Período Selecionado: **{anos_lep_txt}** | Agravo: **Leptospirose (SINAN / DATASUS)** | Métrica: **{modo_mapa_lepto}**")

        tot_lep = int(df_lep_view["total_ano"].sum())
        media_lep = df_lep_view["total_ano"].mean()
        pico_idx = df_lep_view["total_ano"].idxmax()
        ano_pico = int(df_lep_view.loc[pico_idx, "ano"])
        casos_pico = int(df_lep_view.loc[pico_idx, "total_ano"])

        lkpi1, lkpi2, lkpi3 = st.columns(3)
        lkpi1.metric(f"Total Acumulado ({anos_lep_txt})", f"{tot_lep:,}".replace(",", "."))
        lkpi2.metric("Média Anual no Recife", f"{media_lep:.1f} casos/ano")
        lkpi3.metric("Ano de Maior Ocorrência", f"{ano_pico} ({casos_pico} casos)")

        st.markdown("---")

        with st.expander("ℹ️ Entenda a vulnerabilidade socioespacial e por que a Leptospirose explode nas cheias do Recife", expanded=False):
            st.markdown("""
            ### 🐀 O que é a Leptospirose e como ela afeta a nossa saúde?
            A **Leptospirose** é uma infecção febril aguda causada por bactérias do gênero **_Leptospira_**. No ambiente urbano do Recife, a bactéria é eliminada principalmente pela urina de ratos de esgoto (*Rattus norvegicus*). Em períodos chuvosos, a urina contamina águas pluviais, esgotos transbordados e lamas residuais. A infecção ocorre pela penetração ativa da bactéria através da pele (principalmente se houver arranhões ou cortes, ou com contato prolongado com a pele amolecida pela água) ou mucosas (olhos, nariz e boca).

            * **Fase Precoce (Anictérica):** Apresenta-se como um quadro gripal repentino com febre alta, calafrios, dor de cabeça constante e mal-estar geral. Um sinal clínico clássico é a **dor intensa nas panturrilhas (batata da perna)**, que costuma dificultar até a caminhada.
            * **Fase Tardia (Síndrome de Weil):** Ocorre em cerca de 10% a 15% dos pacientes infectados e é de alta letalidade. Provoca o colapso dos rins (insuficiência renal aguda), **icterícia intensa** (pele e olhos em tom alaranjado escuro) e hemorragias sistêmicas, especialmente a **hemorragia pulmonar maciça**, necessitando de suporte imediato em UTI e hemodiálise.

            ---

            ### 🌧️ Por que a Leptospirose explode em certos territórios do Recife?
            A leptospirose não se distribui de maneira uniforme pela cidade. Sua incidência é um dos indicadores mais diretos da **desigualdade socioespacial e da vulnerabilidade hidro-ambiental**:

            * **Geomorfologia e Planícies Aluviais (DS V e DS VIII):** O **Distrito Sanitário V (Bacia do Rio Tejipió)** e o **Distrito Sanitário VIII (Ibura/Jordão/Cohab)** concentram cotas altimétricas baixas e áreas de várzea. Quando os rios Tejipió, Jiquiá e Jordão transbordam, bairros como *Tejipió, Coqueiral, Areias, Jardim São Paulo e Ibura* enfrentam inundações que permanecem por dias, multiplicando o tempo de contato da população com a água contaminada.
            * **Topografia de Morros e Drenagem em Encostas (DS II e DS VII):** Na Zona Norte e Noroeste (*Água Fria, Dois Unidos, Nova Descoberta, Passarinho*), a ocupação desordenada de encostas e vales sem rede coletora faz com que valas a céu aberto e canais de microdrenagem transbordem em dias de temporal torrencial, arrastando roedores e detritos morro abaixo.
            * **Saneamento Incompleto e Gestão de Resíduos:** O descarte irregular de resíduos sólidos e a proximidade com canais assoreados oferecem oferta farta de alimento e abrigo para as colônias de roedores (os 4 "As" do controle de pragas: alimento, água, abrigo e acesso).

            ---

            ### 🗺️ Por que a análise espacial e temporal integrada é fundamental?
            Compreender o comportamento espacial e histórico da leptospirose no Recife permite salvar vidas de forma estratégica:

            * **Janela Sazonal de Alerta Precoce:** O monitoramento mensal comprova que a janela entre **abril e julho** (inverno pernambucano) concentra a quase totalidade dos casos graves. Isso define o cronograma em que a Prefeitura deve intensificar as ações de desratização química preventiva e dragagem de canais antes que as cheias comecem.
            * **Identificação de Hotspots para Doxiperfilaxia:** Nas áreas mapeadas como de alto risco, a Defesa Civil e a Vigilância em Saúde conseguem planejar a distribuição rápida de botas impermeáveis e a quimioprofilaxia com antibióticos (doxiciclina) pós-exposição aguda em populações ribeirinhas que limparam lama pós-inundação.
            * **Memória Histórica de Desastres (2022):** O pico de **565 casos em 2022** documenta cartograficamente que a letalidade de eventos climáticos extremos vai muito além dos deslizamentos imediatos de barreiras: as epidemias hídricas pós-desastre configuram uma emergência sanitária prolongada.
            * **Controle Social e Tomada de Decisão:** Transforma estatísticas complexas em mapas claros que mostram exatamente quais bacias hidrográficas e distritos exigem investimentos prioritários em macrodrenagem e reassentamento de famílias em áreas de cota de inundação crônica.

            ---

            🔍 **Nota Metodológica sobre as Bases de Dados:**
            * **Série Histórica Temporal (Anos e Meses):** Extraída diretamente dos microdados oficiais brutos do **SINAN / DATASUS** (Município de Notificação: Recife - 261160).
            * **Distribuição Territorial:** A espacialização no mapa coroplético reflete os coeficientes de incidência e o peso proporcional dos **8 Distritos Sanitários (DS I ao DS VIII)** apurados nos relatórios e boletins epidemiológicos da **Secretaria Executiva de Vigilância à Saúde do Recife (Sesau/Cievs)**. O Ministério da Saúde suprime a identificação de bairros individuais nas bases públicas abertas por sigilo estatístico (LGPD), dada a menor amostragem nominal da doença em comparação às arboviroses.
            """)

        col_mapa_lep, col_rank_lep = st.columns([1.6, 1.0])

        if not df_lepto_bairros.empty:
            gdf_mapa_lep = gdf_bairros.merge(df_lepto_bairros, on="bairro_norm", how="left").fillna({
                "distrito_sanitario": "Outros",
                "casos_estimados": 0,
                "taxa_incidencia_ds": 0.0,
                "nivel_risco": "Não informado"
            })

            if distritos_selecionados:
                gdf_mapa_lep = gdf_mapa_lep[gdf_mapa_lep["distrito_sanitario"].isin(distritos_selecionados)]

            col_met_lep = "taxa_incidencia_ds" if "Incidência" in modo_mapa_lepto else "casos_estimados"
            lbl_met_lep = "Taxa / 100k hab" if "Incidência" in modo_mapa_lepto else "Casos Estimados"

            with col_mapa_lep:
                st.subheader("🗺️ Mapeamento Espacial de Risco por Distrito Sanitário")
                st.caption("💡 **Para que serve:** Mapeia a vulnerabilidade hidro-sanitária. Tons escuros destacam áreas críticas como a Bacia do Tejipió e bacias do Sul.")
                
                val_max_lep = max(float(gdf_mapa_lep[col_met_lep].max()), 1.0) if not gdf_mapa_lep.empty else 1.0
                palette_lep = ["#ffffcc", "#ffeda0", "#feb24c", "#f03b20", "#800026"]
                colormap_lep = cm.LinearColormap(
                    colors=palette_lep,
                    vmin=0,
                    vmax=val_max_lep,
                    caption=f"{lbl_met_lep} (Leptospirose)",
                )

                m_lep = folium.Map(location=[-8.0580, -34.9200], zoom_start=11, tiles="OpenStreetMap")
                m_lep.get_root().html.add_child(folium.Element("""
                    <style>
                    .leaflet-control-attribution svg, .leaflet-control-attribution a[href*="leafletjs.com"], .leaflet-control-attribution .leaflet-attribution-flag { display: none !important; }
                    </style>
                """))

                tooltip_lep = folium.GeoJsonTooltip(
                    fields=[col_nome_bairro, "distrito_sanitario", "nivel_risco", "taxa_incidencia_ds", "casos_estimados"],
                    aliases=["Bairro:", "Distrito Sanitário:", "Grau de Risco:", "Taxa (100k hab):", "Casos Estimados:"],
                    localize=True,
                    style="background-color: #ffffff; color: #111111; border: 1px solid #333; border-radius: 4px; padding: 8px; font-family: sans-serif; font-size: 12px;"
                )

                folium.GeoJson(
                    gdf_mapa_lep,
                    style_function=lambda feature, cmap=colormap_lep, col=col_met_lep: {
                        "fillColor": cmap(feature["properties"][col]),
                        "color": "#222222",
                        "weight": 1.0,
                        "fillOpacity": 0.90,
                    },
                    tooltip=tooltip_lep,
                ).add_to(m_lep)

                colormap_lep.add_to(m_lep)
                st_folium(m_lep, width="100%", height=480)

            with col_rank_lep:
                st.subheader("Distritos Sanitários Críticos")
                st.caption("💡 **Para que serve:** Avalia o volume acumulado em cada Distrito Sanitário da Sesau, apontando as regiões de maior demanda hospitalar.")
                if not df_lepto_ds.empty:
                    df_ds_plot = df_lepto_ds.copy()
                    if distritos_selecionados:
                        df_ds_plot = df_ds_plot[df_ds_plot["distrito"].isin(distritos_selecionados)]

                    df_ds_plot = df_ds_plot.sort_values(by="casos_historicos", ascending=True)
                    fig_ds = px.bar(
                        df_ds_plot,
                        x="casos_historicos",
                        y="distrito",
                        orientation="h",
                        text="casos_historicos",
                        labels={"casos_historicos": "Casos Acumulados", "distrito": ""},
                        color="casos_historicos",
                        color_continuous_scale="Reds",
                    )
                    fig_ds.update_coloraxes(showscale=False)
                    fig_ds.update_layout(
                        showlegend=False,
                        height=480,
                        margin=dict(l=10, r=10, t=10, b=10),
                        xaxis_title="Casos Acumulados (SINAN)",
                        yaxis_title=None,
                        dragmode=False,
                    )
                    fig_ds.update_traces(textposition="inside", insidetextanchor="middle")
                    st.plotly_chart(fig_ds, use_container_width=True, config=plotly_config)

        st.markdown("---")

        col_t1, col_t2 = st.columns([1.2, 1.0])

        with col_t1:
            st.subheader(f"📈 Evolução Histórica Anual ({anos_lep_txt})")
            st.caption("💡 **Para que serve:** Identifica a correlação entre desastres hidrológicos extremos e surtos infecciosos no município.")
            fig_bar_lep = px.bar(
                df_lep_view,
                x="ano",
                y="total_ano",
                text="total_ano",
                labels={"ano": "Ano", "total_ano": "Casos Confirmados"},
                color="total_ano",
                color_continuous_scale="Reds",
            )
            fig_bar_lep.update_coloraxes(showscale=False)
            fig_bar_lep.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=20, b=10),
                xaxis=dict(
                    tickmode="array",
                    tickvals=anos_lep_sel if len(anos_lep_sel) > 1 else None,
                    tickformat="d",
                    fixedrange=True,
                ),
                yaxis=dict(fixedrange=True),
                dragmode=False,
            )
            fig_bar_lep.update_traces(textposition="outside")
            st.plotly_chart(fig_bar_lep, use_container_width=True, config=plotly_config)

        with col_t2:
            st.subheader("Padrão Sazonal Médio por Mês")
            st.caption("💡 **Para que serve:** Demonstra a quadra chuvosa como gatilho epidemiológico, alertando sobre a época exata de prevenção.")
            meses_nomes = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            cols_meses_validas = [
                c for c in df_lep_view.columns 
                if any(m.lower()[:3] in c.lower() for m in meses_nomes) and "total" not in c.lower()
            ]

            if not cols_meses_validas:
                cols_meses_validas = [
                    c for c in df_lep_view.columns 
                    if c not in ["ano", "total_ano", "Total"] and not c.startswith("LEPTOSPIROSE")
                ]

            media_mes = df_lep_view[cols_meses_validas].mean().reset_index()
            media_mes.columns = ["Mês", "Média"]
            media_mes["Mês"] = media_mes["Mês"].str.slice(0, 3)

            fig_sazonal = px.bar(
                media_mes,
                x="Mês",
                y="Média",
                text="Média",
                labels={"Média": "Média de Casos"},
                color="Média",
                color_continuous_scale="Reds",
            )
            fig_sazonal.update_coloraxes(showscale=False)
            fig_sazonal.update_traces(texttemplate='%{text:.1f}', textposition="outside")
            fig_sazonal.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=20, b=10),
                xaxis=dict(fixedrange=True),
                yaxis=dict(fixedrange=True),
                dragmode=False,
            )
            st.plotly_chart(fig_sazonal, use_container_width=True, config=plotly_config)

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

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #888888; font-size: 13px; line-height: 1.6; padding-bottom: 20px;'>
        <b>Painel de Vigilância Epidemiológica e Análise Espaço-Temporal (Recife - PE)</b><br>
        Desenvolvimento autoral: <b>Luan Lucena</b> | Graduando em Geografia (Bacharelado) pela <b>Universidade Federal de Pernambuco (UFPE)</b> | Membro do <b>Grupo NEXUS (Sociedade & Natureza)</b><br>
        Fontes: Portal de Dados Abertos do Recife (PCR) e Sistema de Informação de Agravos de Notificação (SINAN / DATASUS)<br>
        <span style="color: #38BDF8;">Dúvidas, sugestões ou feedbacks?</span> Entre em contato: <a href="mailto:luan.lucena@ufpe.br" style="color: #38BDF8; text-decoration: underline;">luan.lucena@ufpe.br</a>
    </div>
    """,
    unsafe_allow_html=True,
)
EOF