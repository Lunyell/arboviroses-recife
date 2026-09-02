import os
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# 1. Carregar a malha do Recife
mesh_path = "data/raw/recife_bairros_rpa.gpkg"
if not os.path.exists(mesh_path):
    mesh_path = "../data/raw/recife_bairros_rpa.gpkg"

gdf = gpd.read_file(mesh_path)
if gdf.crs is None or gdf.crs.to_epsg() != 31985:
    gdf = gdf.to_crs(epsg=31985)

contorno_recife = gdf.unary_union

# 2. Configurar a figura quadrada (1:1)
bg_color = "#070B14"
fig, ax = plt.subplots(figsize=(6, 6), facecolor=bg_color, dpi=300)
ax.set_facecolor(bg_color)

# 3. Plotagem das camadas
gdf.plot(
    ax=ax,
    facecolor="#0F172A",
    edgecolor="#1E293B",
    linewidth=0.5,
    zorder=2
)

y_min, y_max = gdf.total_bounds[1], gdf.total_bounds[3]
for idx, row in gdf.iterrows():
    fator = (row.geometry.centroid.y - y_min) / (y_max - y_min)
    if fator < 0.35:
        cor_fill = "#1E1B4B"
        borda = "#38BDF8"
        alpha_val = 0.6
    else:
        cor_fill = "#0F172A"
        borda = "#1E293B"
        alpha_val = 0.4
    
    gpd.GeoSeries([row.geometry]).plot(
        ax=ax,
        facecolor=cor_fill,
        edgecolor=borda,
        linewidth=0.6,
        alpha=alpha_val,
        zorder=3
    )

# Contorno externo brilhante
gpd.GeoSeries([contorno_recife]).plot(
    ax=ax,
    facecolor="none",
    edgecolor="#38BDF8",
    linewidth=1.8,
    zorder=4
)

# Glow externo
gpd.GeoSeries([contorno_recife]).plot(
    ax=ax,
    facecolor="none",
    edgecolor="#0284C7",
    linewidth=4.5,
    alpha=0.35,
    zorder=3
)

# 4. Centralização e enquadramento
bounds = gdf.total_bounds
cx = (bounds[0] + bounds[2]) / 2
cy = (bounds[1] + bounds[3]) / 2
max_range = max(bounds[2] - bounds[0], bounds[3] - bounds[1]) * 0.72

ax.set_xlim(cx - max_range, cx + max_range)
ax.set_ylim(cy - max_range, cy + max_range)
ax.set_axis_off()

plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
nome_perfil = "perfil_observatorio.png"
plt.savefig(
    nome_perfil,
    dpi=300,
    facecolor=bg_color,
    edgecolor="none"
)
plt.close()

print(f"✨ Foto de perfil gerada com sucesso: {nome_perfil}")
