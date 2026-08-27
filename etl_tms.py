import snowflake.connector
from cryptography.hazmat.primitives import serialization
import pymssql
import csv
import os
import sys
import datetime
import time

# === CONFIGURACOES SQL SERVER (Zoho TMS) ===
TMS_SERVER = '10.1.11.11'
TMS_USER = 'bi.zoho'
TMS_PASSWORD = '1ufT@b1z0ho'

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
DELAY_ENTRE_TABELAS = 5
MARGEM_DIAS = 2

# === TABELAS/VIEWS A EXTRAIR ===
# (database, schema, tabela/view, nome_tabela_bronze, modo, coluna_data, etl_control_name)
EXTRAIR = [
    # Full load (views de status/snapshot)
    ('dtbTransporte', 'dbo', 'view_backlog_filiais', 'BACKLOG_FILIAIS_TMS_RAW', 'full', None, None),
    ('dtbTransporte', 'dbo', 'view_backlog_NF_ocorrencias', 'BACKLOG_NF_OCORRENCIAS_TMS_RAW', 'full', None, None),
    ('dtbTransporte', 'dbo', 'view_backlog_ocorrencias', 'BACKLOG_OCORRENCIAS_TMS_RAW', 'full', None, None),
    ('dtbTransporte', 'dbo', 'view_finalizados_NF_ocorrencias', 'FINALIZADOS_NF_OCORRENCIAS_TMS_RAW', 'full', None, None),
    ('dtbTransporte', 'dbo', 'view_PosicoesVeiculos_Zeus', 'POSICOES_VEICULOS_TMS_RAW', 'full', None, None),
    ('dtbTransporte', 'dbo', 'view_problemas_mecanicos', 'PROBLEMAS_MECANICOS_TMS_RAW', 'full', None, None),
    ('dtbTransporte', 'dbo', 'view_relatoriosextras_ops30', 'OPS30_TMS_RAW', 'full', None, None),
    ('dtbTransporte', 'dbo', 'view_transito_NF_ocorrencias', 'TRANSITO_NF_OCORRENCIAS_TMS_RAW', 'full', None, None),
    ('dtbTransporte', 'dbo', 'view_relatoriosextras_calculorentabilidade', 'CALCULO_RENTABILIDADE_TMS_RAW', 'full', None, None),
    # Incremental (tabelas grandes com data)
    ('dtbTransporte', 'dbo', 'view_Relatorio_Ocorrencias_SAC', 'OCORRENCIAS_SAC_TMS_RAW', 'incremental', 'DT_INCLUSAO', 'TMS_OCORRENCIAS_SAC'),
    ('dtbTransporte', 'dbo', 'view_etl_Manifestos_OPs_Rentabilidade', 'MANIFESTOS_OPS_RENTABILIDADE_TMS_RAW', 'incremental', 'DT_ALTERACAO', 'TMS_MANIFESTOS_OPS'),
    ('dtbTransporte', 'dbo', 'view_ordens_servico', 'ORDENS_SERVICO_TMS_RAW', 'incremental', 'DATA_OS', 'TMS_ORDENS_SERVICO'),
    # ('Exporta', 'dbo', 'Telemetry', 'TELEMETRY_TMS_RAW', 'full', None, None),  # Dados antigos (2023-2024) - removido por Alynne
    ('Exporta', 'dbo', 'InformationRegionsLog', 'INFORMATION_REGIONS_TMS_RAW', 'incremental', 'EventDateTime', 'TMS_INFORMATION_REGIONS'),
    ('Exporta', 'dbo', 'PositionHistory_IIPOS', 'POSITION_HISTORY_TMS_RAW', 'incremental_7', 'IIPOS_TimePosition', 'TMS_POSITION_HISTORY'),
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


def conectar_tms():
    return pymssql.connect(server=TMS_SERVER, user=TMS_USER, password=TMS_PASSWORD)


def get_ultima_data(sf_conn, api_name):
    cur = sf_conn.cursor()
    cur.execute(f"SELECT ULTIMA_DATA_CARGA FROM {SF_DB}.{SF_SCHEMA}.ETL_CONTROL WHERE API_NAME = '{api_name}'")
    row = cur.fetchone()
    if row:
        return row[0]
    return None


def set_ultima_data(sf_conn, api_name, data):
    cur = sf_conn.cursor()
    cur.execute(f"""
        UPDATE {SF_DB}.{SF_SCHEMA}.ETL_CONTROL 
        SET ULTIMA_DATA_CARGA = '{data}', UPDATED_AT = CURRENT_TIMESTAMP()
        WHERE API_NAME = '{api_name}'
    """)


def get_colunas_tms(tms_conn, database, schema, tabela):
    cur = tms_conn.cursor()
    cur.execute(f"""
        SELECT COLUMN_NAME 
        FROM [{database}].INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{tabela}'
        ORDER BY ORDINAL_POSITION
    """)
    return [row[0] for row in cur.fetchall()]


def extrair_dados_tms(tms_conn, database, schema, tabela, where_clause=None, batch_size=500000):
    cur = tms_conn.cursor()
    base_query = f'SELECT * FROM [{database}].[{schema}].[{tabela}]'
    count_query = f'SELECT COUNT(*) FROM [{database}].[{schema}].[{tabela}]'
    if where_clause:
        base_query += f' WHERE {where_clause}'
        count_query += f' WHERE {where_clause}'

    cur.execute(count_query)
    total = cur.fetchone()[0]
    log(f'Total de registros a extrair: {total}')

    if total == 0:
        return [], 0

    if total <= batch_size:
        cur.execute(base_query)
        return cur.fetchall(), total
    else:
        log(f'Tabela grande ({total} registros) - extraindo em lotes de {batch_size}')
        rows = []
        offset = 0
        while offset < total:
            cur.execute(f"""
                {base_query}
                ORDER BY (SELECT NULL)
                OFFSET {offset} ROWS FETCH NEXT {batch_size} ROWS ONLY
            """)
            batch = cur.fetchall()
            rows.extend(batch)
            offset += batch_size
            log(f'  Lote extraido: {len(rows)}/{total}')
        return rows, total


def sanitizar_coluna(col):
    import re
    col = col.upper().replace(' ', '_')
    col = re.sub(r'[^A-Z0-9_]', '', col)
    if not col or col[0].isdigit():
        col = 'C_' + col
    return col


def criar_tabela_bronze(sf_conn, tabela_bronze, colunas):
    cur = sf_conn.cursor()
    cols_ddl = ',\n    '.join([f'{sanitizar_coluna(col)} VARCHAR' for col in colunas])
    ddl = f"""
        CREATE TABLE IF NOT EXISTS {SF_DB}.{SF_SCHEMA}.{tabela_bronze} (
            {cols_ddl},
            NM_FONTE VARCHAR DEFAULT 'ZOHO_TMS',
            DT_CARGA TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """
    cur.execute(ddl)
    log(f'Tabela {tabela_bronze} verificada/criada')


def carregar_snowflake(sf_conn, arquivo_csv, tabela_bronze, colunas):
    cur = sf_conn.cursor()
    stage = f'@{SF_DB}.{SF_SCHEMA}.STG_LANDING/tms/'

    # PUT
    arquivo_path = arquivo_csv.replace('\\', '/')
    cur.execute(f"PUT 'file://{arquivo_path}' {stage} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")

    # COPY INTO
    num_cols = len(colunas)
    cols_select = ','.join([f'${i}' for i in range(1, num_cols + 1)])
    cols_destino = ','.join([sanitizar_coluna(col) for col in colunas])
    
    nome_arquivo = os.path.basename(arquivo_csv)
    cur.execute(f"""
        COPY INTO {SF_DB}.{SF_SCHEMA}.{tabela_bronze} ({cols_destino})
        FROM (
            SELECT {cols_select}
            FROM {stage}
        )
        FILE_FORMAT = (TYPE=CSV SKIP_HEADER=1 FIELD_OPTIONALLY_ENCLOSED_BY='"' NULL_IF=('None','NULL',''))
        PATTERN = '.*{nome_arquivo}.*'
        ON_ERROR = 'CONTINUE'
    """)

    # Contar registros
    cur.execute(f'SELECT COUNT(*) FROM {SF_DB}.{SF_SCHEMA}.{tabela_bronze}')
    qt = cur.fetchone()[0]
    log(f'{tabela_bronze}: {qt} registros carregados')
    return qt


def registrar_log(sf_conn, tabela, modo, status, registros, erro=None):
    cur = sf_conn.cursor()
    erro_str = str(erro).replace("'", "''")[:500] if erro else ''
    cur.execute(f"""
        INSERT INTO {SF_DB}.{SF_SCHEMA}.ETL_LOG 
        (DT_INICIO, DT_FIM, NM_TABELA, DS_MODO, QT_EXTRAIDOS, QT_CARREGADOS, DS_STATUS, DS_ERRO, DS_FILTRO)
        VALUES (CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), '{tabela}', '{modo}', {registros}, {registros}, '{status}', '{erro_str}', 'ETL TMS')
    """)


def processar_tabela(tms_conn, sf_conn, database, schema, tabela, tabela_bronze, modo, coluna_data, etl_control_name):
    log(f'--- Processando {database}.{schema}.{tabela} -> {tabela_bronze} ({modo}) ---')

    try:
        # 1. Descobrir colunas
        colunas = get_colunas_tms(tms_conn, database, schema, tabela)
        if not colunas:
            log(f'AVISO: Nenhuma coluna encontrada para {tabela}. Pulando.')
            return 0
        log(f'Colunas: {len(colunas)}')

        # 2. Montar filtro incremental
        where_clause = None
        if modo == 'incremental' and etl_control_name:
            ultima_data = get_ultima_data(sf_conn, etl_control_name)
            if ultima_data:
                dt_filtro = (ultima_data - datetime.timedelta(days=MARGEM_DIAS)).strftime('%Y-%m-%d')
                where_clause = f"{coluna_data} >= '{dt_filtro}'"
                log(f'Incremental: {where_clause}')
        elif modo == 'incremental_90':
            dt_90 = (datetime.date.today() - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
            where_clause = f"{coluna_data} >= '{dt_90}'"
            log(f'Janela 90 dias: {where_clause}')
        elif modo == 'incremental_7':
            dt_7 = (datetime.date.today() - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
            where_clause = f"{coluna_data} >= '{dt_7}'"
            log(f'Janela 7 dias: {where_clause}')

        # 3. Extrair dados
        dados, total_origem = extrair_dados_tms(tms_conn, database, schema, tabela, where_clause)
        log(f'Registros extraidos: {len(dados)}')

        if len(dados) == 0:
            log(f'Nenhum registro. Pulando.')
            registrar_log(sf_conn, tabela_bronze, modo, 'SUCESSO', 0)
            return 0

        # 4. Salvar CSV
        os.makedirs(CSV_DIR, exist_ok=True)
        arquivo_csv = os.path.join(CSV_DIR, f'{tabela_bronze.lower()}.csv')
        with open(arquivo_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(colunas)
            for row in dados:
                writer.writerow([str(val) if val is not None else '' for val in row])
        log(f'CSV salvo: {arquivo_csv}')

        # 5. Criar tabela se nao existe
        criar_tabela_bronze(sf_conn, tabela_bronze, colunas)

        # 6. Preparar destino
        sf_cur = sf_conn.cursor()
        if modo in ('full', 'incremental_90', 'incremental_7'):
            sf_cur.execute(f'TRUNCATE TABLE {SF_DB}.{SF_SCHEMA}.{tabela_bronze}')
            log(f'Tabela truncada ({modo})')
        elif modo == 'incremental' and where_clause:
            col_sf = sanitizar_coluna(coluna_data)
            dt_filtro = (get_ultima_data(sf_conn, etl_control_name) - datetime.timedelta(days=MARGEM_DIAS)).strftime('%Y-%m-%d')
            sf_cur.execute(f"DELETE FROM {SF_DB}.{SF_SCHEMA}.{tabela_bronze} WHERE TRY_TO_TIMESTAMP({col_sf}) >= '{dt_filtro}'")
            log(f'Deletados registros >= {dt_filtro}')

        # 7. Carregar no Snowflake
        qt = carregar_snowflake(sf_conn, arquivo_csv, tabela_bronze, colunas)

        # 8. Atualizar ETL_CONTROL
        if modo == 'incremental' and etl_control_name:
            hoje = datetime.date.today().strftime('%Y-%m-%d')
            set_ultima_data(sf_conn, etl_control_name, hoje)

        # 9. Registrar sucesso
        registrar_log(sf_conn, tabela_bronze, modo, 'SUCESSO', qt)

        # 10. Limpar CSV
        os.remove(arquivo_csv)

        return qt

    except Exception as e:
        log(f'ERRO ao processar {tabela}: {e}')
        registrar_log(sf_conn, tabela_bronze, modo, 'ERRO', 0, e)
        return 0


def main():
    log('=== INICIO ETL ZOHO TMS ===')

    # Argumento opcional: python etl_tms.py --apenas=BACKLOG_FILIAIS_TMS_RAW
    apenas = None
    for arg in sys.argv:
        if arg.startswith('--apenas='):
            apenas = arg.split('=')[1].upper()

    sf_conn = conectar_snowflake()
    tms_conn = conectar_tms()

    try:
        total = 0
        for database, schema, tabela, tabela_bronze, modo, coluna_data, etl_control_name in EXTRAIR:
            if apenas and apenas != tabela_bronze:
                continue
            qt = processar_tabela(tms_conn, sf_conn, database, schema, tabela, tabela_bronze, modo, coluna_data, etl_control_name)
            total += qt
            if qt > 0:
                time.sleep(DELAY_ENTRE_TABELAS)

        log(f'=== ETL TMS CONCLUIDO: {total} registros totais ===')

    except Exception as e:
        log(f'ERRO GERAL: {e}')
    finally:
        tms_conn.close()
        sf_conn.close()


if __name__ == '__main__':
    main()
