import io
import os
import pandas as pd
from playwright.sync_api import sync_playwright

DEST_DIR = os.path.join("data", "raw")
os.makedirs(DEST_DIR, exist_ok=True)
DEST_CSV = os.path.join(DEST_DIR, "leptospirose_recife_sinan.csv")

URL_TABNET = "http://tabnet.datasus.gov.br/cgi/deftohtm.exe?sinannet/cnv/leptope.def"

print("🚀 Abrindo navegador Playwright...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    print("🌐 Acessando TabNet Leptospirose (PE)...")
    page.goto(URL_TABNET, timeout=60000)
    page.wait_for_selector("select#L", timeout=15000)

    print("⚡ Configurando parâmetros: Linha=Ano, Coluna=Mês, Filtro=Recife...")
    # Linha: Ano do 1º Sintoma
    page.select_option("select#L", value="Ano_1º_Sintoma(s)")

    # Coluna: Mês do 1º Sintoma
    page.select_option("select#C", value="Mês_1º_Sintoma(s)")

    # Incremento: Casos confirmados
    page.select_option("select#I", value="Casos_confirmados")

    # Marca todos os arquivos históricos (.dbf)
    arquivos = page.eval_on_selector_all("select#A option", "opts => opts.map(o => o.value)")
    if arquivos:
        page.select_option("select#A", value=arquivos)

    # Filtro Município de Residência = Recife (261160)
    page.evaluate('''() => {
        const selMun = document.querySelector("select#S11") || document.querySelector("select[name='SMunicípio_de_residência']");
        if (selMun) {
            for (let opt of selMun.options) {
                if (opt.value.includes("261160") || opt.text.includes("Recife")) {
                    opt.selected = true;
                    break;
                }
            }
        }
    }''')

    print("📊 Executando consulta no DATASUS...")
    with context.expect_page() as popup_info:
        page.eval_on_selector("input[type='submit'], input[name='mostra'], input[value*='Mostra']", "btn => btn.click()")

    result_page = popup_info.value
    result_page.wait_for_load_state("networkidle", timeout=60000)
    html_content = result_page.content()
    text_content = result_page.inner_text("body")
    browser.close()

# Parser de fallback: tenta ler as tabelas HTML geradas
df_final = None

try:
    tabelas = pd.read_html(io.StringIO(html_content), decimal=",", thousands=".")
    for t in tabelas:
        # A tabela principal de resultados contém colunas de meses ou anos
        if len(t.columns) > 3 and len(t) > 2:
            df_final = t
            break
except Exception:
    pass

# Se não pegou via HTML, tenta via texto delimitado (PRN/CSV)
if df_final is None or len(df_final) == 0:
    linhas = [l for l in text_content.splitlines() if ";" in l]
    if len(linhas) > 1:
        try:
            df_final = pd.read_csv(io.StringIO("\n".join(linhas)), sep=";", quotechar='"', low_memory=False)
        except Exception:
            pass

if df_final is not None:
    # Limpeza básica de nomes de colunas
    df_final.columns = [str(c).strip().replace('"', '') for c in df_final.columns]
    df_final = df_final.replace("-", 0)
    
    df_final.to_csv(DEST_CSV, index=False, sep=";", encoding="utf-8")
    print(f"\n🎉 Sucesso! Base de Leptospirose salva em: {DEST_CSV}")
    print(f"📊 Dimensão da tabela: {df_final.shape}")
    print("\nVisualização das primeiras linhas:")
    print(df_final.head(10))
else:
    # Grava o HTML bruto para diagnóstico caso falhe
    with open(DEST_CSV, "w", encoding="utf-8") as f:
        f.write(text_content)
    print(f"⚠️ Não foi possível tabular diretamente. Arquivo bruto salvo em: {DEST_CSV}")