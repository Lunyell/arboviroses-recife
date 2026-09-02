import ast
import os
import pandas as pd

RAW_CSV = os.path.join("data", "raw", "leptospirose_recife_sinan.csv")
PROCESSED_DIR = os.path.join("data", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(PROCESSED_DIR, "leptospirose_recife_mensal.csv")

print("🧹 Processando e estruturando os dados de Leptospirose...")

# 1. Lê com cabeçalho simples
df = pd.read_csv(RAW_CSV, sep=";", low_memory=False)
if len(df.columns) == 1:
    df = pd.read_csv(RAW_CSV, sep=",", low_memory=False)

# 2. Desempacota nomes de colunas que viraram string de tupla
novas_colunas = []
for c in df.columns:
    c_str = str(c).strip()
    if c_str.startswith("(") and c_str.endswith(")"):
        try:
            tupla = ast.literal_eval(c_str)
            col_name = str(tupla[1]).strip()
            if "Unnamed" in col_name or col_name == "nan" or not col_name:
                col_name = str(tupla[0]).strip()
        except Exception:
            col_name = c_str
    else:
        col_name = c_str
    novas_colunas.append(col_name)

df.columns = novas_colunas

# 3. Renomeia a primeira coluna para 'ano'
df.rename(columns={df.columns[0]: "ano"}, inplace=True)

# 4. Remove colunas com 'Unnamed' ou vazias
colunas_validas = [c for c in df.columns if not str(c).startswith("Unnamed") and str(c) != "nan"]
df = df[colunas_validas].copy()

# 5. Descarta linhas de Total geral ou metadados
df = df[~df["ano"].astype(str).str.upper().str.contains("TOTAL")].copy()

# 6. Filtra apenas registros com anos válidos de 4 dígitos (2007 em diante)
df = df[df["ano"].astype(str).str.strip().str.match(r"^\d{4}$")].copy()
df["ano"] = df["ano"].astype(int)
df = df.sort_values("ano").reset_index(drop=True)

# 7. Identifica colunas de meses e converte valores para inteiro
meses_cols = [c for c in df.columns if c.lower() not in ["ano", "total"]]

for c in meses_cols:
    df[c] = pd.to_numeric(
        df[c].astype(str).str.replace("-", "0").str.strip(),
        errors="coerce"
    ).fillna(0).astype(int)

# 8. Cria coluna com soma total de cada ano
df["total_ano"] = df[meses_cols].sum(axis=1)

# Salva matriz consolidada
df.to_csv(OUTPUT_CSV, index=False, sep=";", encoding="utf-8")

# Salva formato longo para plotagem rápida
OUTPUT_LONG = os.path.join(PROCESSED_DIR, "leptospirose_recife_long.csv")
df_long = df.melt(id_vars=["ano"], value_vars=meses_cols, var_name="mes", value_name="casos")
df_long.to_csv(OUTPUT_LONG, index=False, sep=";", encoding="utf-8")

print("🎉 Processamento concluído com sucesso!")
print(f"📁 Matriz limpa: {OUTPUT_CSV}")
print(f"📁 Série longa:  {OUTPUT_LONG}")
print("\n📊 Casos confirmados de Leptospirose por ano no Recife:")
print(df[["ano", "total_ano"]].to_string(index=False))