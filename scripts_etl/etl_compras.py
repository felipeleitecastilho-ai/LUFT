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
SF_STAGE = '@DRE_AGENTE_ALL.BRONZE.STG_LANDING/compras_protheus/'
SF_TABLE = 'DRE_AGENTE_ALL.BRONZE.COMPRAS_PROTHEUS_RAW'

# === CONFIGURACOES GERAIS ===
BASE_DIR = r'C:\Users\keyrus\etl_luft'
CSV_DIR = os.path.join(BASE_DIR, 'temp')
LAST_RUN_FILE = os.path.join(BASE_DIR, 'last_run.txt')
BATCH_SIZE = 50000
MARGEM_DIAS = 2

def log(msg):
    print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}')

def get_last_run():
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, 'r') as f:
            return f.read().strip()
    return None

def set_last_run(data):
    with open(LAST_RUN_FILE, 'w') as f:
        f.write(data)

def extrair_oracle():
    log('Conectando ao Oracle...')
    conn = oracledb.connect(user=ORA_USER, password=ORA_PASS, dsn=ORA_DSN)
    cur = conn.cursor()

    last_run = get_last_run()

    if last_run:
        # Incremental: pega da ultima execucao - margem
        dt_last = datetime.datetime.strptime(last_run, '%Y%m%d')
        dt_filtro = (dt_last - datetime.timedelta(days=MARGEM_DIAS)).strftime('%Y%m%d')
        log(f'Modo INCREMENTAL: DTDIGIT >= {dt_filtro} (last_run={last_run}, margem={MARGEM_DIAS} dias)')
        query = f"SELECT * FROM U_C1JTKS_PR.DATALAKE_COMPRAS WHERE LUFT_F1_DTDIGIT >= '{dt_filtro}'"
        cur.execute(f"SELECT COUNT(*) FROM U_C1JTKS_PR.DATALAKE_COMPRAS WHERE LUFT_F1_DTDIGIT >= '{dt_filtro}'")
    else:
        # Full load (primeira execucao)
        log('Modo FULL LOAD (primeira execucao, sem last_run.txt)')
        query = "SELECT * FROM U_C1JTKS_PR.DATALAKE_COMPRAS"
        cur.execute('SELECT COUNT(*) FROM U_C1JTKS_PR.DATALAKE_COMPRAS')

    total = cur.fetchone()[0]
    log(f'Registros a extrair: {total}')

    if total == 0:
        log('Nenhum registro novo. Encerrando.')
        conn.close()
        return []

    cur.execute(query)
    colunas = [col[0] for col in cur.description]

    os.makedirs(CSV_DIR, exist_ok=True)
    arquivos = []
    batch_num = 0

    while True:
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        batch_num += 1
        arquivo = os.path.join(CSV_DIR, f'compras_batch_{batch_num}.csv')
        with open(arquivo, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(colunas)
            writer.writerows(rows)
        arquivos.append(arquivo)
        log(f'Batch {batch_num}: {len(rows)} linhas -> {arquivo}')

    conn.close()
    log(f'Extracao finalizada: {batch_num} arquivo(s)')
    return arquivos

def carregar_snowflake(arquivos):
    log('Conectando ao Snowflake...')
    with open(SF_KEY_PATH, 'rb') as key_file:
        private_key = serialization.load_pem_private_key(key_file.read(), password=None)
    conn = snowflake.connector.connect(
        account=SF_ACCOUNT,
        user=SF_USER,
        private_key=private_key,
        warehouse=SF_WH,
        database=SF_DB,
        schema=SF_SCHEMA
    )
    cur = conn.cursor()

    # Estrategia: DELETE + INSERT (sem chave unica natural na view)
    # Deleta registros do periodo e reinsere com dados atualizados
    last_run = get_last_run()
    if last_run:
        dt_last = datetime.datetime.strptime(last_run, '%Y%m%d')
        dt_filtro = (dt_last - datetime.timedelta(days=MARGEM_DIAS)).strftime('%Y%m%d')
        log(f'DELETE registros com DTDIGIT >= {dt_filtro}...')
        cur.execute(f"DELETE FROM {SF_TABLE} WHERE LUFT_F1_DTDIGIT >= '{dt_filtro}'")
        resultado = cur.fetchone()
        log(f'Deletados: {resultado[0]} linhas')

    # Limpa stage antes de subir novos arquivos
    cur.execute(f"REMOVE {SF_STAGE}")
    log('Stage limpo')

    # PUT de todos os arquivos primeiro
    for arquivo in arquivos:
        nome = os.path.basename(arquivo)
        log(f'PUT {nome}...')
        arquivo_path = arquivo.replace('\\', '/')
        cur.execute(f"PUT 'file://{arquivo_path}' {SF_STAGE} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")

    # COPY INTO unico (carrega todos de uma vez)
    log('COPY INTO...')
    cur.execute(f"""
        COPY INTO {SF_TABLE}
        FROM (
            SELECT METADATA$FILENAME::TEXT, CURRENT_TIMESTAMP(),
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
                $19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36
            FROM {SF_STAGE}
        )
        FILE_FORMAT = (FORMAT_NAME = 'DRE_AGENTE_ALL.BRONZE.CSV_FORMAT')
        FORCE = TRUE
    """)
    for row in cur.fetchall():
        log(f'Resultado: {row[1]} - {row[2]} linhas')

    conn.close()
    log('Carga Snowflake finalizada!')

def limpar_temp(arquivos):
    for arquivo in arquivos:
        os.remove(arquivo)
    log('Arquivos temporarios removidos')

if __name__ == '__main__':
    log('=== INICIO ETL COMPRAS PROTHEUS -> SNOWFLAKE ===')
    try:
        arquivos = extrair_oracle()
        if arquivos:
            carregar_snowflake(arquivos)
            limpar_temp(arquivos)
            # Atualiza last_run com data de hoje
            hoje = datetime.datetime.now().strftime('%Y%m%d')
            set_last_run(hoje)
            log(f'last_run.txt atualizado: {hoje}')
        log('=== ETL CONCLUIDO COM SUCESSO ===')
    except Exception as e:
        log(f'ERRO: {e}')
        raise
