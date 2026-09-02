import glob
import io
import os
import unicodedata
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

# 1. Função de normalização de texto
def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join([c for c in texto if not unicodedata.combining(c)])
    return texto.strip().upper()

# 2. Parsing robusto para desmembrar o CSV híbrido de 2015 e ler 2016-2024
def extrair_bairros_do_csv(caminho):
    try:
        df_raw = pd.read_csv(caminho, sep=";", encoding="utf-8", low_memory=False)
    except Exception:
        df_raw = pd.read_csv(caminho, sep=";", encoding="latin1", low_memory=False)

    df_raw.columns = [str(c).lower().strip() for c in df_raw.columns]
    col_combo = [c for c in df_raw.columns if "," in c]

    dfs_extraidos = []

    # Se tiver a coluna com registros de 2015 concatenados por vírgula
    if col_combo:
        col_c = col_combo[0]
        serie_combo = df_raw[col_c].dropna().astype(str)
        if len(serie_combo) > 0:
            linhas_texto = [col_c] + serie_combo.tolist()
            buffer = io.StringIO("\n".join(linhas_texto))
            try:
                df_sub = pd.read_csv(buffer, sep=",", low_memory=False, on_bad_lines="skip")
                df_sub.columns = [str(c).lower().strip() for c in df_sub.columns]
                dfs_extraidos.append(df_sub)
            except Exception:
                pass

        df_principal = df_raw.drop(columns=[col_c]).dropna(how="all")
        dfs_extraidos.append(df_principal)
    else:
        dfs_extraidos.append(df_raw)

    bairros = []
    for d in dfs_extraidos:
        if d.empty:
            continue
        col_b = next((c for c in ["no_bairro_residencia", "nm_bairro", "bairro", "ds_bairro", "nome_bairro", "bairro_norm"] if c in d.columns), None)
        if col_b:
            s_bairro = d[col_b].dropna().apply(normalizar_texto)
            s_bairro = s_bairro[s_bairro != ""]
            bairros.append(s_bairro)

    if bairros:
        return pd.concat(bairros, ignore_index=True)
    return pd.Series([], dtype=str)

# 3. Carregar a malha vetorial dos bairros do Recife
mesh_path = "data/raw/recife_bairros_rpa.gpkg"
if not os.path.exists(mesh_path):
    mesh_path = "../data/raw/recife_bairros_rpa.gpkg"

gdf_malha = gpd.read_file(mesh_path)

if gdf_malha.crs is None or gdf_malha.crs.to_epsg() != 31985:
    gdf_malha = gdf_malha.to_crs(epsg=31985)

col_nome = "name_neighborhood" if "name_neighborhood" in gdf_malha.columns else gdf_malha.columns[1]
gdf_malha["bairro_norm"] = gdf_malha[col_nome].apply(normalizar_texto)

# 4. Ler e totalizar todos os CSVs (2015-2024)
raw_dir = "data/raw" if os.path.exists("data/raw") else "../data/raw"
arquivos_csv = sorted(glob.glob(os.path.join(raw_dir, "arboviroses_*.csv")))
todos_bairros = []

for caminho in arquivos_csv:
    serie = extrair_bairros_do_csv(caminho)
    if not serie.empty:
        todos_bairros.append(serie)

df_total = pd.DataFrame({"bairro_norm": pd.concat(todos_bairros, ignore_index=True)})

# 5. Totalizar as notificações decenais reais por bairro
contagem = df_total["bairro_norm"].value_counts().reset_index()
contagem.columns = ["bairro_norm", "total_casos"]

# 6. Merge com a malha vetorial oficial
gdf_mapa = gdf_malha.merge(contagem, on="bairro_norm", how="left")
gdf_mapa["total_casos"] = gdf_mapa["total_casos"].fillna(0)

print(f"📊 Total de notificações contabilizadas (2015-2024): {int(gdf_mapa['total_casos'].sum()):,}")

# 7. Paleta e Estilo Dark
cores_paleta = ["#FEF0D9", "#FDCC8A", "#FC8D59", "#E34A33", "#B30000"]
cmap_custom = LinearSegmentedColormap.from_list("painel_stream", cores_paleta)

bg_color = "#0B0F19"
card_color = "#151C2C"
text_color = "#E2E8F0"
subtext_color = "#94A3B8"

fig, ax = plt.subplots(figsize=(10, 10), facecolor=bg_color)
ax.set_facecolor(bg_color)

# 8. Plotagem Coroplética com Quebras Naturais (Jenks / NaturalBreaks)
gdf_mapa.plot(
    column="total_casos",
    cmap=cmap_custom,
    scheme="NaturalBreaks",
    k=5,
    edgecolor="#334155",
    linewidth=0.6,
    legend=True,
    legend_kwds={
        "loc": "center",
        "frameon": True,
        "facecolor": card_color,
        "edgecolor": "#334155",
        "title": "Notificações Acumuladas",
        "title_fontsize": "9.5",
        "fontsize": "8.5",
    },
    ax=ax,
)

# 9. Posicionamento da Legenda na margem direita
legend = ax.get_legend()
if legend:
    plt.setp(legend.get_texts(), color=text_color)
    plt.setp(legend.get_title(), color=text_color, fontweight="bold")
    legend.set_bbox_to_anchor((0.85, 0.28), transform=fig.transFigure)

# 10. Escala Gráfica Dinâmica
bounds = gdf_mapa.total_bounds
dx = bounds[2] - bounds[0]
dy = bounds[3] - bounds[1]

scale_x = bounds[0] + dx * 0.02
scale_y = bounds[1] + dy * 0.02
scale_len = 5000

ax.plot(
    [scale_x, scale_x + scale_len / 2],
    [scale_y, scale_y],
    color="#F8FAFC",
    lw=3.5,
    solid_capstyle="butt",
)
ax.plot(
    [scale_x + scale_len / 2, scale_x + scale_len],
    [scale_y, scale_y],
    color="#475569",
    lw=3.5,
    solid_capstyle="butt",
)
ax.text(scale_x, scale_y - 450, "0", color=text_color, fontsize=8, ha="center", va="top")
ax.text(scale_x + scale_len / 2, scale_y - 450, "2.5", color=text_color, fontsize=8, ha="center", va="top")
ax.text(scale_x + scale_len, scale_y - 450, "5 km", color=text_color, fontsize=8, ha="center", va="top")

# 11. Rosa dos Ventos
north_x = scale_x + scale_len / 2
north_y = scale_y + 1400
ax.annotate(
    "N",
    xy=(north_x, north_y),
    xytext=(north_x, north_y - 800),
    arrowprops=dict(facecolor="#F8FAFC", edgecolor="none", width=2, headwidth=6),
    ha="center",
    va="center",
    fontsize=9.5,
    fontweight="bold",
    color=text_color,
)

# 12. Título e Metadados Cartográficos
fig.text(
    0.08,
    0.93,
    "DISTRIBUIÇÃO ESPACIAL DAS ARBOVIROSES",
    fontsize=13.5,
    fontweight="bold",
    color=text_color,
    ha="left",
)
fig.text(
    0.08,
    0.90,
    "Recife (PE) • Acumulado Decenal de Notificações (2015–2024)",
    fontsize=10,
    color="#38BDF8",
    ha="left",
)
fig.text(
    0.08,
    0.875,
    "Agravos: Dengue, Chikungunya e Zika Vírus",
    fontsize=8.5,
    color=subtext_color,
    ha="left",
)

metadados = (
    "Sistema de Referência: SIRGAS 2000 / UTM zone 25S (EPSG:31985)\n"
    "Fonte de Dados: Secretaria de Saúde do Recife / Sinan (2015–2024)\n"
    "Cartografia: Observatório de Saúde Urbana do Recife | Luan Lucena"
)
fig.text(0.08, 0.04, metadados, fontsize=7.5, color=subtext_color, ha="left")

# 13. Salvar Imagem em Alta Resolução
ax.set_axis_off()
plt.subplots_adjust(left=0.04, right=0.96, top=0.85, bottom=0.08)

nome_saida = "mapa_arboviroses_recife_oficial.png"
plt.savefig(
    nome_saida,
    dpi=300,
    facecolor=fig.get_facecolor(),
    edgecolor="none",
)
print(f"✨ Mapa decenal oficial (2015-2024) gerado com sucesso: {nome_saida}")