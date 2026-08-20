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
SF_WH = 'ETL_WH'
SF_DB = 'DRE_AGENTE_ALL'
SF_SCHEMA = 'BRONZE'

# === CONFIGURACOES GERAIS ===
BASE_DIR = r'C:\Users\keyrus\etl_luft'
CSV_DIR = os.path.join(BASE_DIR, 'temp')
LAST_RUN_FILE = os.path.join(BASE_DIR, 'last_run.txt')
BATCH_SIZE = 50000
MARGEM_DIAS = 2

# === TABELAS ===
TABELAS = [
    {
        'nome': 'COMPRAS',
        'view_oracle': 'U_C1JTKS_PR.DATALAKE_COMPRAS',
        'tabela_sf': 'DRE_AGENTE_ALL.BRONZE.COMPRAS_PROTHEUS_RAW',
        'stage': '@DRE_AGENTE_ALL.BRONZE.STG_LANDING/compras_protheus/',
        'num_colunas': 36,
        'modo': 'incremental',
        'coluna_data': 'LUFT_F1_DTDIGIT',
    },
    {
        'nome': 'EMPRESAS',
        'view_oracle': 'U_C1JTKS_PR.DATALAKE_EMPRESAS',
        'tabela_sf': 'DRE_AGENTE_ALL.BRONZE.EMPRESAS_PROTHEUS_RAW',
        'stage': '@DRE_AGENTE_ALL.BRONZE.STG_LANDING/empresas_protheus/',
        'num_colunas': 8,
        'modo': 'full',
    },
    {
        'nome': 'FORNECEDOR',
        'view_oracle': 'U_C1JTKS_PR.DATALAKE_FORNECEDOR',
        'tabela_sf': 'DRE_AGENTE_ALL.BRONZE.FORNECEDOR_PROTHEUS_RAW',
        'stage': '@DRE_AGENTE_ALL.BRONZE.STG_LANDING/fornecedor_protheus/',
        'num_colunas': 9,
        'modo': 'full',
    },
    {
        'nome': 'PRODUTOS',
        'view_oracle': 'U_C1JTKS_PR.DATALAKE_PRODUTOS',
        'tabela_sf': 'DRE_AGENTE_ALL.BRONZE.PRODUTOS_PROTHEUS_RAW',
        'stage': '@DRE_AGENTE_ALL.BRONZE.STG_LANDING/produtos_protheus/',
        'num_colunas': 5,
        'modo': 'full',
    },
]

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

def registrar_log(sf_conn, nm_tabela, ds_modo, dt_inicio, dt_fim, qt_extraidos, qt_deletados, qt_carregados, ds_status, ds_erro, ds_filtro):
    duracao = int((dt_fim - dt_inicio).total_seconds())
    cur = sf_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {nm_tabela}" if ds_status == 'SUCESSO' else "SELECT 0")
    qt_total = cur.fetchone()[0] if ds_status == 'SUCESSO' else 0
    cur.execute(f"""
        INSERT INTO DRE_AGENTE_ALL.BRONZE.ETL_LOG 
        (DT_INICIO, DT_FIM, NM_TABELA, DS_MODO, QT_EXTRAIDOS, QT_DELETADOS, QT_CARREGADOS, QT_TOTAL_TABELA, DS_STATUS, DS_ERRO, DS_FILTRO, QT_DURACAO_SEG)
        VALUES ('{dt_inicio.strftime("%Y-%m-%d %H:%M:%S")}', '{dt_fim.strftime("%Y-%m-%d %H:%M:%S")}', 
                '{nm_tabela}', '{ds_modo}', {qt_extraidos}, {qt_deletados}, {qt_carregados}, {qt_total},
                '{ds_status}', {f"'{ds_erro}'" if ds_erro else 'NULL'}, {f"'{ds_filtro}'" if ds_filtro else 'NULL'}, {duracao})
    """)

def processar_tabela(tab, sf_conn):
    nome = tab['nome']
    modo = tab['modo']
    dt_inicio = datetime.datetime.now()
    qt_extraidos = 0
    qt_deletados = 0
    qt_carregados = 0
    ds_filtro = None

    log(f'--- {nome} ({modo}) ---')

    try:
        # Conexao Oracle
        ora_conn = oracledb.connect(user=ORA_USER, password=ORA_PASS, dsn=ORA_DSN)
        cur = ora_conn.cursor()

        # Montar query
        if modo == 'incremental':
            last_run = get_last_run()
            if last_run:
                dt_last = datetime.datetime.strptime(last_run, '%Y%m%d')
                dt_filtro = (dt_last - datetime.timedelta(days=MARGEM_DIAS)).strftime('%Y%m%d')
                ds_filtro = f"{tab['coluna_data']} >= {dt_filtro}"
                log(f'Incremental: {ds_filtro}')
                query = f"SELECT * FROM {tab['view_oracle']} WHERE {tab['coluna_data']} >= '{dt_filtro}'"
                count_query = f"SELECT COUNT(*) FROM {tab['view_oracle']} WHERE {tab['coluna_data']} >= '{dt_filtro}'"
            else:
                log('Full load (primeira execucao)')
                query = f"SELECT * FROM {tab['view_oracle']}"
                count_query = f"SELECT COUNT(*) FROM {tab['view_oracle']}"
        else:
            query = f"SELECT * FROM {tab['view_oracle']}"
            count_query = f"SELECT COUNT(*) FROM {tab['view_oracle']}"

        cur.execute(count_query)
        qt_extraidos = cur.fetchone()[0]
        log(f'Registros: {qt_extraidos}')

        if qt_extraidos == 0:
            log('Nenhum registro. Pulando.')
            ora_conn.close()
            dt_fim = datetime.datetime.now()
            registrar_log(sf_conn, tab['tabela_sf'], modo, dt_inicio, dt_fim, 0, 0, 0, 'SUCESSO', None, ds_filtro)
            return 0

        # Extrair
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
            arquivo = os.path.join(CSV_DIR, f'{nome.lower()}_batch_{batch_num}.csv')
            with open(arquivo, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(colunas)
                writer.writerows(rows)
            arquivos.append(arquivo)
            log(f'Batch {batch_num}: {len(rows)} linhas')

        ora_conn.close()

        # Carregar no Snowflake
        sf_cur = sf_conn.cursor()

        # DELETE ou TRUNCATE conforme modo
        if modo == 'incremental' and get_last_run():
            dt_last = datetime.datetime.strptime(get_last_run(), '%Y%m%d')
            dt_filtro = (dt_last - datetime.timedelta(days=MARGEM_DIAS)).strftime('%Y%m%d')
            sf_cur.execute(f"DELETE FROM {tab['tabela_sf']} WHERE {tab['coluna_data']} >= '{dt_filtro}'")
            qt_deletados = sf_cur.fetchone()[0]
            log(f'Deletados: {qt_deletados} linhas')
        elif modo == 'full':
            sf_cur.execute(f"TRUNCATE TABLE {tab['tabela_sf']}")
            log('Tabela truncada')

        # Limpa stage
        sf_cur.execute(f"REMOVE {tab['stage']}")

        # PUT todos os arquivos
        for arquivo in arquivos:
            arquivo_path = arquivo.replace('\\', '/')
            sf_cur.execute(f"PUT 'file://{arquivo_path}' {tab['stage']} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")

        # COPY INTO
        cols_select = ','.join([f'${i}' for i in range(1, tab['num_colunas'] + 1)])
        sf_cur.execute(f"""
            COPY INTO {tab['tabela_sf']}
            FROM (
                SELECT METADATA$FILENAME::TEXT, CURRENT_TIMESTAMP(), {cols_select}
                FROM {tab['stage']}
            )
            FILE_FORMAT = (FORMAT_NAME = 'DRE_AGENTE_ALL.BRONZE.CSV_FORMAT')
            FORCE = TRUE
        """)
        for row in sf_cur.fetchall():
            qt_carregados += row[2]
        log(f'Carregado: {qt_carregados} linhas')

        # Limpa temp
        for arquivo in arquivos:
            os.remove(arquivo)

        log(f'{nome} concluido')
        dt_fim = datetime.datetime.now()
        registrar_log(sf_conn, tab['tabela_sf'], modo, dt_inicio, dt_fim, qt_extraidos, qt_deletados, qt_carregados, 'SUCESSO', None, ds_filtro)
        return qt_carregados

    except Exception as e:
        dt_fim = datetime.datetime.now()
        log(f'ERRO em {nome}: {e}')
        registrar_log(sf_conn, tab['tabela_sf'], modo, dt_inicio, dt_fim, qt_extraidos, qt_deletados, qt_carregados, 'ERRO', str(e)[:500], ds_filtro)
        raise

if __name__ == '__main__':
    log('=== INICIO ETL PROTHEUS -> SNOWFLAKE ===')
    sf_conn = conectar_snowflake()
    try:
        total_geral = 0
        for tab in TABELAS:
            total_geral += processar_tabela(tab, sf_conn)

        # Atualiza last_run (usado pelo incremental de COMPRAS)
        hoje = datetime.datetime.now().strftime('%Y%m%d')
        set_last_run(hoje)
        log(f'last_run.txt atualizado: {hoje}')
        log(f'=== ETL CONCLUIDO: {total_geral} registros totais ===')
    except Exception as e:
        log(f'ERRO GERAL: {e}')
    finally:
        sf_conn.close()
