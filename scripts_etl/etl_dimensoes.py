import oracledb
import snowflake.connector
from cryptography.hazmat.primitives import serialization
import csv
import os
import datetime

# === CONFIGURACOES ORACLE ===
ORA_USER = 'consulta'
ORA_PASS = 'pvcqh92861VCPME@!'
ORA_DSN = '201.157.213.136:1521/C1JTKS_192934_P'

# === CONFIGURACOES SNOWFLAKE (Key Pair Auth) ===
SF_ACCOUNT = 'zqlozdv-chc24786'
SF_USER = 'ETL_PROTHEUS'
SF_KEY_PATH = r'C:\Users\keyrus\etl_luft\snowflake_key.p8'
SF_WH = 'COMPUTE_WH'
SF_DB = 'DRE_AGENTE_ALL'
SF_SCHEMA = 'BRONZE'

# === CONFIGURACOES GERAIS ===
BASE_DIR = r'C:\Users\keyrus\etl_luft'
CSV_DIR = os.path.join(BASE_DIR, 'temp')
BATCH_SIZE = 50000

# === TABELAS DIMENSAO (full load: truncate + reload) ===
DIMENSOES = [
    {
        'nome': 'EMPRESAS',
        'view_oracle': 'U_C1JTKS_PR.DATALAKE_EMPRESAS',
        'tabela_sf': 'DRE_AGENTE_ALL.BRONZE.EMPRESAS_PROTHEUS_RAW',
        'stage': '@DRE_AGENTE_ALL.BRONZE.STG_LANDING/empresas_protheus/',
        'num_colunas': 8,
    },
    {
        'nome': 'FORNECEDOR',
        'view_oracle': 'U_C1JTKS_PR.DATALAKE_FORNECEDOR',
        'tabela_sf': 'DRE_AGENTE_ALL.BRONZE.FORNECEDOR_PROTHEUS_RAW',
        'stage': '@DRE_AGENTE_ALL.BRONZE.STG_LANDING/fornecedor_protheus/',
        'num_colunas': 9,
    },
    {
        'nome': 'PRODUTOS',
        'view_oracle': 'U_C1JTKS_PR.DATALAKE_PRODUTOS',
        'tabela_sf': 'DRE_AGENTE_ALL.BRONZE.PRODUTOS_PROTHEUS_RAW',
        'stage': '@DRE_AGENTE_ALL.BRONZE.STG_LANDING/produtos_protheus/',
        'num_colunas': 5,
    },
]

def log(msg):
    print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}')

def conectar_snowflake():
    with open(SF_KEY_PATH, 'rb') as key_file:
        private_key = serialization.load_pem_private_key(key_file.read(), password=None)
    return snowflake.connector.connect(
        account=SF_ACCOUNT,
        user=SF_USER,
        private_key=private_key,
        warehouse=SF_WH,
        database=SF_DB,
        schema=SF_SCHEMA
    )

def processar_dimensao(dim):
    nome = dim['nome']
    log(f'--- {nome} ---')

    # Extrair do Oracle
    log(f'Extraindo {dim["view_oracle"]}...')
    ora_conn = oracledb.connect(user=ORA_USER, password=ORA_PASS, dsn=ORA_DSN)
    cur = ora_conn.cursor()

    cur.execute(f'SELECT COUNT(*) FROM {dim["view_oracle"]}')
    total = cur.fetchone()[0]
    log(f'Registros: {total}')

    cur.execute(f'SELECT * FROM {dim["view_oracle"]}')
    colunas = [col[0] for col in cur.description]

    os.makedirs(CSV_DIR, exist_ok=True)
    arquivos = []
    batch_num = 0

    while True:
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        batch_num += 1
        arquivo = os.path.join(CSV_DIR, f'{nome.lower()}_batch_{batch_num}.csv')
        with open(arquivo, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(colunas)
            writer.writerows(rows)
        arquivos.append(arquivo)
        log(f'Batch {batch_num}: {len(rows)} linhas')

    ora_conn.close()

    # Carregar no Snowflake (truncate + reload)
    log(f'Carregando no Snowflake...')
    sf_conn = conectar_snowflake()
    sf_cur = sf_conn.cursor()

    # Truncate
    sf_cur.execute(f'TRUNCATE TABLE {dim["tabela_sf"]}')
    log('Tabela truncada')

    # Limpa stage
    sf_cur.execute(f'REMOVE {dim["stage"]}')

    # PUT todos os arquivos
    for arquivo in arquivos:
        arquivo_path = arquivo.replace('\\', '/')
        sf_cur.execute(f"PUT 'file://{arquivo_path}' {dim['stage']} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")

    # COPY INTO
    cols_select = ','.join([f'${i}' for i in range(1, dim['num_colunas'] + 1)])
    sf_cur.execute(f"""
        COPY INTO {dim['tabela_sf']}
        FROM (
            SELECT METADATA$FILENAME::TEXT, CURRENT_TIMESTAMP(), {cols_select}
            FROM {dim['stage']}
        )
        FILE_FORMAT = (FORMAT_NAME = 'DRE_AGENTE_ALL.BRONZE.CSV_FORMAT')
        FORCE = TRUE
    """)
    for row in sf_cur.fetchall():
        log(f'Resultado: {row[1]} - {row[2]} linhas')

    sf_conn.close()

    # Limpa temp
    for arquivo in arquivos:
        os.remove(arquivo)

    log(f'{nome} concluido: {total} registros')
    return total

if __name__ == '__main__':
    log('=== INICIO ETL DIMENSOES PROTHEUS -> SNOWFLAKE ===')
    try:
        total_geral = 0
        for dim in DIMENSOES:
            total_geral += processar_dimensao(dim)
        log(f'=== ETL DIMENSOES CONCLUIDO: {total_geral} registros totais ===')
    except Exception as e:
        log(f'ERRO: {e}')
        raise
