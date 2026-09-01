import os
import glob
import unicodedata
import pandas as pd
import geopandas as gpd

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
os.makedirs(PROCESSED_DIR, exist_ok=True)

def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto_str = str(texto).strip().upper()
    nfkd = unicodedata.normalize("NFKD", texto_str)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])

print("[-] Carregando malha espacial dos bairros...")
mesh_path = os.path.join(RAW_DIR, "recife_bairros_rpa.gpkg")
gdf_bairros = gpd.read_file(mesh_path)

col_bairro_mesh = "name_neighborhood" if "name_neighborhood" in gdf_bairros.columns else gdf_bairros.columns[1]
gdf_bairros["bairro_norm"] = gdf_bairros[col_bairro_mesh].apply(normalizar_texto)

csv_files = sorted(glob.glob(os.path.join(RAW_DIR, "arboviroses_*.csv")))
df_list = []

print("[-] Processando datasets anuais com as colunas corretas de nomes...")

for file_path in csv_files:
    ano_arquivo = int(os.path.basename(file_path).replace("arboviroses_", "").replace(".csv", ""))
    
    try:
        df = pd.read_csv(file_path, sep=";", encoding="latin1", low_memory=False)
        if len(df.columns) <= 1:
            df = pd.read_csv(file_path, sep=",", encoding="latin1", low_memory=False)
    except Exception:
        df = pd.read_csv(file_path, sep=";", encoding="utf-8", low_memory=False)

    df.columns = [c.strip().lower() for c in df.columns]

    # Mapeamento explícito das colunas de nome de bairro
    col_alvo = None
    if "no_bairro_residencia" in df.columns:
        col_alvo = "no_bairro_residencia"
    elif "nm_bairro" in df.columns:
        col_alvo = "nm_bairro"
    elif "no_bairro_infeccao" in df.columns:
        col_alvo = "no_bairro_infeccao"

    if col_alvo:
        bairros_serie = df[col_alvo].apply(normalizar_texto)
        df_temp = pd.DataFrame({"ano": ano_arquivo, "bairro_norm": bairros_serie})
        
        # Filtrar registros vazios ou sem bairro definido
        df_temp = df_temp[df_temp["bairro_norm"] != ""]
        
        contagem = df_temp.groupby(["ano", "bairro_norm"]).size().reset_index(name="total_casos")
        df_list.append(contagem)
        print(f"[✓] {ano_arquivo}: {len(df)} notificações lidas (Coluna: '{col_alvo}') -> {len(contagem)} bairros com casos")
    else:
        print(f"[!] Erro ao mapear coluna no ano {ano_arquivo}")

# Concatenar todos os anos
df_consolidado = pd.concat(df_list, ignore_index=True)

# Salvar tabela processada agregada em GPKG
output_painel = os.path.join(PROCESSED_DIR, "recife_arboviroses_painel.gpkg")
gdf_painel = gdf_bairros.merge(df_consolidado, on="bairro_norm", how="inner")
gdf_painel.to_file(output_painel, driver="GPKG")

print(f"[✓] Dataset final salvo com sucesso em: {output_painel}")