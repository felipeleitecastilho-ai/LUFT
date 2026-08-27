"""
Script para parsear arquivos DRE brutos (formato sistema) para formato Bronze Snowflake.
Entrada: CSVs brutos com 6 linhas de header e 160+ colunas
Saida: CSVs limpos com 47 colunas no formato Bronze
"""
import csv
import os
import re

INPUT_DIR = r"C:\Users\Felipe.Santos\OneDrive - Keyrus\Área de Trabalho\PROJETOS\LUFT\DRE"
OUTPUT_DIR = r"C:\Users\Felipe.Santos\OneDrive - Keyrus\Área de Trabalho\PROJETOS\LUFT\DRE_PROCESSADO"

os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADER = [
    "NM_ARQUIVO","FILIAL","ANO_REFERENCIA","MES_BASE","ILOC","CONTA_NOME","NUMERO_CONTA",
    "JAN_ANT_R","JAN_ATU_P","JAN_ATU_R",
    "FEV_ANT_R","FEV_ATU_P","FEV_ATU_R",
    "MAR_ANT_R","MAR_ATU_P","MAR_ATU_R",
    "ABR_ANT_R","ABR_ATU_P","ABR_ATU_R",
    "MAI_ANT_R","MAI_ATU_P","MAI_ATU_R",
    "JUN_ANT_R","JUN_ATU_P","JUN_ATU_R",
    "JUL_ANT_R","JUL_ATU_P","JUL_ATU_R",
    "AGO_ANT_R","AGO_ATU_P","AGO_ATU_R",
    "SET_ANT_R","SET_ATU_P","SET_ATU_R",
    "OUT_ANT_R","OUT_ATU_P","OUT_ATU_R",
    "NOV_ANT_R","NOV_ATU_P","NOV_ATU_R",
    "DEZ_ANT_R","DEZ_ATU_P","DEZ_ATU_R",
    "ACUM_ANT_R","ACUM_ATU_P","ACUM_ATU_R"
]

def extract_filial_from_filename(filename):
    match = re.search(r'DRE \d{4} -\s*(.+)\.csv', filename)
    if match:
        return match.group(1).strip()
    match = re.search(r'DRE \d{4}-\s*(.+)\.csv', filename)
    if match:
        return match.group(1).strip()
    return filename.replace('.csv', '')

def extract_metadata(lines):
    line3 = lines[2]
    mes_base_match = re.search(r'M.S BASE:\s*,?(\d+)', line3)
    mes_base = int(mes_base_match.group(1)) if mes_base_match else 12
    
    line5 = lines[4]
    cols5 = line5.split(',')
    ano_ref = None
    for col in cols5:
        col = col.strip()
        if col and re.match(r'\d{4}R', col):
            year = int(col[:4])
            if ano_ref is None or year > ano_ref:
                ano_ref = year
    # ano_ref is the "current year" (the one with P and R)
    # Look for the pattern YYYYP to find current year
    for col in cols5:
        col = col.strip()
        if col and re.match(r'\d{4}P', col):
            ano_ref = int(col[:4])
            break
    
    return mes_base, ano_ref

def parse_dre_file(filepath):
    filename = os.path.basename(filepath)
    filial = extract_filial_from_filename(filename)
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()
    
    mes_base, ano_ref = extract_metadata(lines)
    
    rows = []
    iloc = 0
    for line in lines[6:]:  # Skip 6 header lines
        parts = line.strip().split(',')
        if not parts or not parts[0].strip():
            continue
        
        conta_nome = parts[0].strip()
        if not conta_nome or conta_nome.upper() in ('', ' '):
            continue
            
        numero_conta = parts[1].strip() if len(parts) > 1 else ''
        iloc += 1
        
        # Extract 39 value columns (positions 2-40, 0-indexed in parts)
        values = []
        for i in range(2, min(41, len(parts))):
            val = parts[i].strip() if i < len(parts) else ''
            values.append(val)
        
        # Pad to 39 if needed
        while len(values) < 39:
            values.append('')
        
        row = [filename, filial, str(ano_ref), str(mes_base), str(iloc), conta_nome, numero_conta] + values[:39]
        rows.append(row)
    
    return rows

# Process all files
all_rows = []
files = sorted([f for f in os.listdir(INPUT_DIR) if f.endswith('.csv')])
print(f"Processando {len(files)} arquivos...")

for filename in files:
    filepath = os.path.join(INPUT_DIR, filename)
    rows = parse_dre_file(filepath)
    all_rows.extend(rows)
    print(f"  {filename}: {len(rows)} linhas, filial={extract_filial_from_filename(filename)}")

# Write single output file
output_path = os.path.join(OUTPUT_DIR, "DRE_ALL.csv")
with open(output_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(HEADER)
    writer.writerows(all_rows)

print(f"\nTotal: {len(all_rows)} linhas escritas em {output_path}")
print(f"Colunas: {len(HEADER)}")
