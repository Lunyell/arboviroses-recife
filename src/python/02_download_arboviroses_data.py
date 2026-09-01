import os
import requests

OUTPUT_DIR = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)

SEARCH_API = "http://dados.recife.pe.gov.br/api/3/action/package_search?q=dengue&rows=50"
headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

print("[-] Buscando datasets de arboviroses no catálogo de dados do Recife...")

res = requests.get(SEARCH_API, headers=headers, timeout=30)
if res.status_code != 200:
    print(f"[!] Erro ao conectar na API de busca: Status {res.status_code}")
    exit(1)

packages = res.json().get("result", {}).get("results", [])
print(f"[+] Total de pacotes encontrados: {len(packages)}")

anos_alvo = [str(a) for a in range(2015, 2025)]
baixados = set()

for pkg in packages:
    pkg_title = pkg.get("title", "")
    for resource in pkg.get("resources", []):
        res_name = resource.get("name", "")
        res_url = resource.get("url", "")
        res_format = resource.get("format", "").lower()

        if "csv" in res_format or res_url.lower().endswith(".csv"):
            for ano in anos_alvo:
                if (ano in res_name or ano in res_url or ano in pkg_title) and ano not in baixados:
                    dest_path = os.path.join(OUTPUT_DIR, f"arboviroses_{ano}.csv")
                    print(f"[-] Baixando {ano} ({res_name}) ...")
                    try:
                        file_req = requests.get(res_url, headers=headers, timeout=60)
                        if file_req.status_code == 200 and len(file_req.content) > 1000:
                            with open(dest_path, "wb") as f:
                                f.write(file_req.content)
                            print(f"[✓] {ano} salvo com sucesso ({len(file_req.content)/(1024*1024):.2f} MB)")
                            baixados.add(ano)
                        else:
                            print(f"[!] Erro no download do ano {ano} (Status: {file_req.status_code})")
                    except Exception as e:
                        print(f"[x] Falha ao baixar {ano}: {e}")

print(f"[✓] Finalizado! Total de anos baixados: {len(baixados)}/10")