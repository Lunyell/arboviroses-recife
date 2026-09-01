import glob
import os
import unicodedata
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

# 1. Função de normalização de texto idêntica ao app.py
def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join([c for c in texto if not unicodedata.combining(c)])
    return texto.strip().upper()

# 2. Carregar a malha vetorial dos bairros do Recife
mesh_path = "data/raw/recife_bairros_rpa.gpkg"
gdf_malha = gpd.read_file(mesh_path)

if gdf_malha.crs is None or gdf_malha.crs.to_epsg() != 31985:
    gdf_malha = gdf_malha.to_crs(epsg=31985)

gdf_malha["bairro_norm"] = gdf_malha["name_neighborhood"].apply(normalizar_texto)

# 3. Ler e concatenar todos os CSVs de 2015 a 2024
arquivos_csv = sorted(glob.glob("data/raw/arboviroses_*.csv"))
dfs = []

for caminho in arquivos_csv:
    try:
        df_temp = pd.read_csv(caminho, sep=";", encoding="utf-8", low_memory=False)
    except Exception:
        df_temp = pd.read_csv(caminho, sep=";", encoding="latin1", low_memory=False)
    
    # Padronização dos nomes de colunas
    df_temp.columns = [c.lower().strip() for c in df_temp.columns]
    
    # Identificar coluna de bairro
    col_b = None
    for c in ["bairro", "no_bairro", "nome_bairro", "ds_bairro", "nm_bairro", "bairro_norm"]:
        if c in df_temp.columns:
            col_b = c
            break
            
    if col_b:
        df_temp["bairro_norm"] = df_temp[col_b].apply(normalizar_texto)
        dfs.append(df_temp[["bairro_norm"]])

df_total = pd.concat(dfs, ignore_index=True)

# 4. Totalizar as notificações decenais reais (2015-2024) por bairro
contagem = df_total["bairro_norm"].value_counts().reset_index()
contagem.columns = ["bairro_norm", "total_casos"]

# 5. Merge com a malha vetorial oficial
gdf_mapa = gdf_malha.merge(contagem, on="bairro_norm", how="left")
gdf_mapa["total_casos"] = gdf_mapa["total_casos"].fillna(0)

# 6. Paleta e Estilo Dark
cores_paleta = ["#FEF0D9", "#FDCC8A", "#FC8D59", "#E34A33", "#B30000"]
cmap_custom = LinearSegmentedColormap.from_list("painel_stream", cores_paleta)

bg_color = "#0B0F19"
card_color = "#151C2C"
text_color = "#E2E8F0"
subtext_color = "#94A3B8"

fig, ax = plt.subplots(figsize=(10, 10), facecolor=bg_color)
ax.set_facecolor(bg_color)

# 7. Plotagem Coroplética
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

# 8. Posicionamento da Legenda na margem direita
legend = ax.get_legend()
if legend:
    plt.setp(legend.get_texts(), color=text_color)
    plt.setp(legend.get_title(), color=text_color, fontweight="bold")
    legend.set_bbox_to_anchor((0.85, 0.28), transform=fig.transFigure)

# 9. Escala Gráfica Dinâmica
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

# 10. Rosa dos Ventos
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

# 11. Título e Metadados Cartográficos
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

# 12. Salvar Imagem
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