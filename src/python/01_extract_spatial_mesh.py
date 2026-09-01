import os
import requests
import json
import geopandas as gpd
import geobr

OUTPUT_DIR = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)
output_gpkg = os.path.join(OUTPUT_DIR, "recife_bairros_rpa.gpkg")

URL_EMPREL = "http://dados.recife.pe.gov.br/dataset/c1f100f0-f56f-4dd4-9dcc-1aa4da2879da/resource/e43be4f7-3195-467b-bc3c-411e9d6c717e/download/bairro.geojson"

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
}

print("[-] Tentando obter malha dos bairros do Recife...")

try:
    res = requests.get(URL_EMPREL, headers=headers, timeout=20)
    data = res.json()
    gdf_bairros = gpd.GeoDataFrame.from_features(data["features"])
    gdf_bairros = gdf_bairros.set_crs(epsg=4326, allow_override=True)
    print("[+] Sucesso via Dados Abertos Recife!")
except Exception as e:
    print(f"[!] Falha no portal municipal ({e}). Carregando malha via geobr...")
    gdf_recife = geobr.read_neighborhood(year=2010)
    gdf_bairros = gdf_recife[gdf_recife['code_muni'] == 2611606].copy()

print(f"[+] Total de polígonos carregados: {len(gdf_bairros)}")
print("[+] Colunas disponíveis:", gdf_bairros.columns.tolist())

gdf_bairros.to_file(output_gpkg, driver="GPKG")
print(f"[✓] Malha espacial salva em: {output_gpkg}")