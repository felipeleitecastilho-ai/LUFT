import snowflake.connector
from cryptography.hazmat.primitives import serialization
import csv
import os
import sys
import datetime
import time
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Modo teste: python etl_silt.py --teste
MODO_TESTE = '--teste' in sys.argv
CNPJ_TESTE = '87689402008884'  # LUFT AGRO AP. DE GOIANIA/GO

# === CONFIGURACOES API SILT ===
API_BASE_URL = 'https://appsagro.luftdigital.com.br'
API_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0eXBlIjoiYXV0aGVudGljYXRpb24iLCJpZCI6ImNtb2JnMWZ5YzAwMDJwbTBvYTEyaWFwc2EiLCJleHBpcmVzQXQiOiIzMDI1LTA4LTI0VDEyOjE0OjQ1LjE3M1oiLCJpYXQiOjE3NzY5NDY0ODUsImV4cCI6MzE1Mzc3NzY5NDY0ODV9.lUmQKJvk_l-bmKlHfsq4jukXLd3jJ138Y9Kz4fguLcw'

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
BATCH_SIZE = 50000

# === COLUNAS POR TABELA ===
COLUNAS_SALDO_ESTOQUE = [
    'ARMAZEM_CNPJCPF', 'ARMAZEM_NOME', 'DEPOSITANTE_CNPJCPF', 'DEPOSITANTE_NOME',
    'DEPOSITANTE_CIDADE', 'DEPOSITANTE_UF', 'DEPOSITANTE_ISAG',
    'NOTAENTRADA_NUMERO', 'NOTAENTRADA_DATAEMISSAO', 'NOTAENTRADA_DATACADASTRO', 'NOTAENTRADA_CFOP',
    'NOTACOBERTURA_NUMERO', 'NOTACOBERTURA_DATAEMISSAO', 'NOTACOBERTURA_DATACADASTRO', 'NOTACOBERTURA_CFOP',
    'PRODUTO_CODIGO', 'PRODUTO_NOME', 'IDLOTE', 'LOTE_INDUSTRIA', 'LOTE_VENCIMENTO', 'DTALOCACAO',
    'CONTRATO_NUMERO', 'PAGADOR_CNPJCPF', 'PAGADOR_NOME',
    'QTDE_ENTRADA', 'QTDE_COBERTO', 'QTDE_SALDO'
]

COLUNAS_NF = [
    'IDARMAZEM', 'ARMAZEM_CNPJCPF', 'ARMAZEM_NOME',
    'DEPOSITANTE_CNPJCPF', 'DEPOSITANTE_NOME', 'DEPOSITANTE_CIDADE', 'DEPOSITANTE_ESTADO',
    'IDNOTAFISCAL', 'ID_DEPOSITANTE', 'NOTA_FISCAL',
    'DATA_EMISSAO', 'DATA_CADASTRO', 'DATA_PROCESSAMENTO', 'NF_TIPO',
    'PAGADOR_CNPJCPF', 'PAGADOR_NOME', 'PAGADOR_PRAZO_DIAS',
    'COD_PRODUTO', 'PRODUTO', 'TIPO_PRODUTO', 'GRUPO',
    'IDLOTE', 'LOTE_INDUSTRIA', 'LOTE_DATAFABRICACAO', 'LOTE_DATAVENCIMENTO',
    'QTDE_LOTE', 'LASTRO', 'UM_EMBALAGEM', 'VALOR_TOTAL', 'PESO_LIQUIDO', 'PESO_BRUTO',
    'REMETENTE_CNPJCPF', 'REMETENTE_NOME', 'REMETENTE_CIDADE', 'REMETENTE_ESTADO',
    'DESTINATARIO_CNPJCPF', 'DESTINATARIO_NOME', 'DESTINATARIO_CIDADE', 'DESTINATARIO_ESTADO'
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


def get_headers():
    return {
        'Authorization': f'Bearer {API_TOKEN}',
        'Accept': 'application/json'
    }


def get_ultima_data(sf_conn, api_name):
    cur = sf_conn.cursor()
    cur.execute(f"SELECT ULTIMA_DATA_CARGA FROM DRE_AGENTE_ALL.BRONZE.ETL_CONTROL WHERE API_NAME = '{api_name}'")
    row = cur.fetchone()
    if row:
        return row[0]
    return datetime.date(2025, 1, 1)


def set_ultima_data(sf_conn, api_name, data):
    cur = sf_conn.cursor()
    cur.execute(f"""
        UPDATE DRE_AGENTE_ALL.BRONZE.ETL_CONTROL 
        SET ULTIMA_DATA_CARGA = '{data}', UPDATED_AT = CURRENT_TIMESTAMP()
        WHERE API_NAME = '{api_name}'
    """)


def chamar_api(endpoint, params=None, max_retries=3):
    url = f'{API_BASE_URL}{endpoint}'
    log(f'Chamando API: {url}')
    if params:
        log(f'Params: {params}')
    
    for tentativa in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=get_headers(), params=params, timeout=900, verify=False)
            response.raise_for_status()
            dados = response.json()
            if isinstance(dados, dict) and 'data' in dados:
                dados = dados['data']
            if not isinstance(dados, list):
                dados = [dados]
            log(f'Registros retornados: {len(dados)}')
            return dados
        except Exception as e:
            if tentativa < max_retries:
                espera = 30 * tentativa
                log(f'Erro na tentativa {tentativa}/{max_retries}: {e}')
                log(f'Aguardando {espera}s antes de tentar novamente...')
                time.sleep(espera)
            else:
                raise


def salvar_csv(dados, colunas, nome_arquivo):
    os.makedirs(CSV_DIR, exist_ok=True)
    arquivo = os.path.join(CSV_DIR, nome_arquivo)
    with open(arquivo, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(colunas)
        for row in dados:
            writer.writerow([row.get(col, None) for col in colunas])
    log(f'CSV salvo: {arquivo} ({len(dados)} linhas)')
    return arquivo


def carregar_snowflake(sf_conn, arquivo, tabela, stage, num_colunas, colunas_destino, truncar=False):
    sf_cur = sf_conn.cursor()

    if truncar:
        sf_cur.execute(f'TRUNCATE TABLE {tabela}')
        log(f'Tabela {tabela} truncada')

    # Limpa stage
    sf_cur.execute(f'REMOVE {stage}')

    # PUT arquivo
    arquivo_path = arquivo.replace('\\', '/')
    sf_cur.execute(f"PUT 'file://{arquivo_path}' {stage} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")

    # COPY INTO com colunas explicitas (exclui DATA_CARGA que tem default)
    cols_select = ','.join([f'${i}' for i in range(1, num_colunas + 1)])
    cols_destino = ','.join(colunas_destino)
    sf_cur.execute(f"""
        COPY INTO {tabela} ({cols_destino})
        FROM (
            SELECT {cols_select}
            FROM {stage}
        )
        FILE_FORMAT = (FORMAT_NAME = 'DRE_AGENTE_ALL.BRONZE.CSV_FORMAT')
        FORCE = TRUE
    """)
    qt_carregados = 0
    for row in sf_cur.fetchall():
        qt_carregados += row[2]
    log(f'Carregado em {tabela}: {qt_carregados} linhas')

    # Limpa CSV
    os.remove(arquivo)
    return qt_carregados


def registrar_log(sf_conn, nm_tabela, ds_modo, dt_inicio, dt_fim, qt_extraidos, qt_deletados, qt_carregados, ds_status, ds_erro, ds_filtro):
    duracao = int((dt_fim - dt_inicio).total_seconds())
    cur = sf_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {nm_tabela}" if ds_status == 'SUCESSO' else "SELECT 0")
    qt_total = cur.fetchone()[0] if ds_status == 'SUCESSO' else 0
    ds_erro_safe = ds_erro.replace("'", "''")[:500] if ds_erro else None
    ds_filtro_safe = ds_filtro.replace("'", "''") if ds_filtro else None
    cur.execute(f"""
        INSERT INTO DRE_AGENTE_ALL.BRONZE.ETL_LOG 
        (DT_INICIO, DT_FIM, NM_TABELA, DS_MODO, QT_EXTRAIDOS, QT_DELETADOS, QT_CARREGADOS, QT_TOTAL_TABELA, DS_STATUS, DS_ERRO, DS_FILTRO, QT_DURACAO_SEG)
        VALUES ('{dt_inicio.strftime("%Y-%m-%d %H:%M:%S")}', '{dt_fim.strftime("%Y-%m-%d %H:%M:%S")}', 
                '{nm_tabela}', '{ds_modo}', {qt_extraidos}, {qt_deletados}, {qt_carregados}, {qt_total},
                '{ds_status}', {f"'{ds_erro_safe}'" if ds_erro_safe else 'NULL'}, {f"'{ds_filtro_safe}'" if ds_filtro_safe else 'NULL'}, {duracao})
    """)


def get_filiais_silt():
    """Chama API sem filtro para descobrir todos os CNPJs de filiais"""
    log('Buscando lista de CNPJs na API de saldo-estoque...')
    dados = chamar_api('/armazem/saldo-estoque')
    cnpjs = list(set(row.get('ARMAZEM_CNPJCPF') for row in dados if row.get('ARMAZEM_CNPJCPF')))
    cnpjs.sort()
    log(f'CNPJs encontrados: {len(cnpjs)}')
    return cnpjs


def get_filiais_fallback(sf_conn):
    """Fallback: busca CNPJs das tabelas de NF"""
    cur = sf_conn.cursor()
    cur.execute("""
        SELECT DISTINCT ARMAZEM_CNPJCPF FROM (
            SELECT ARMAZEM_CNPJCPF FROM DRE_AGENTE_ALL.BRONZE.NF_ENTRADA_SILT_RAW
            UNION
            SELECT ARMAZEM_CNPJCPF FROM DRE_AGENTE_ALL.BRONZE.NF_SAIDA_SILT_RAW
        ) WHERE ARMAZEM_CNPJCPF IS NOT NULL
    """)
    return [row[0] for row in cur.fetchall()]


def processar_saldo_estoque(sf_conn):
    nome = 'SALDO_ESTOQUE_SILT_RAW'
    tabela = f'DRE_AGENTE_ALL.BRONZE.{nome}'
    stage = f'@DRE_AGENTE_ALL.BRONZE.STG_LANDING/saldo_estoque_silt/'
    dt_inicio = datetime.datetime.now()

    log(f'=== {nome} (full load) ===')
    try:
        if MODO_TESTE:
            filiais = [CNPJ_TESTE]
            log(f'MODO TESTE: apenas 1 filial')
        else:
            # Tenta pegar lista de CNPJs da API
            try:
                filiais = get_filiais_silt()
            except Exception as e:
                log(f'Falha ao buscar CNPJs da API: {e}')
                log('Usando fallback (CNPJs das tabelas NF)...')
                filiais = get_filiais_fallback(sf_conn)

            log(f'Total de filiais: {len(filiais)}')

        # Trunca tabela (full load)
        sf_cur = sf_conn.cursor()
        sf_cur.execute(f'TRUNCATE TABLE {tabela}')
        log('Tabela truncada')

        qt_total = 0
        total_registros_api = 0

        for i, cnpj in enumerate(filiais, 1):
            log(f'--- Filial {i}/{len(filiais)}: {cnpj} ---')

            if i > 1:
                time.sleep(15)

            params = {'cnpjFilial': cnpj}
            dados = chamar_api('/armazem/saldo-estoque', params)

            if not dados:
                log(f'Nenhum dado para filial {cnpj}')
                continue

            total_registros_api += len(dados)
            arquivo = salvar_csv(dados, COLUNAS_SALDO_ESTOQUE, f'saldo_estoque_silt_{i}.csv')
            qt = carregar_snowflake(sf_conn, arquivo, tabela, stage, len(COLUNAS_SALDO_ESTOQUE), COLUNAS_SALDO_ESTOQUE, truncar=False)
            qt_total += qt

        dt_fim = datetime.datetime.now()
        registrar_log(sf_conn, tabela, 'full', dt_inicio, dt_fim, total_registros_api, total_registros_api, qt_total, 'SUCESSO', None, f'{len(filiais)} filiais')
        log(f'{nome} concluido: {qt_total} registros totais')
        return qt_total

    except Exception as e:
        dt_fim = datetime.datetime.now()
        log(f'ERRO: {e}')
        registrar_log(sf_conn, tabela, 'full', dt_inicio, dt_fim, 0, 0, 0, 'ERRO', str(e)[:500], None)
        raise


def gerar_periodos_mensais(data_inicio, data_fim):
    """Gera lista de tuplas (inicio, fim) mes a mes"""
    periodos = []
    atual = data_inicio
    while atual < data_fim:
        proximo = (atual.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        fim_periodo = min(proximo - datetime.timedelta(days=1), data_fim)
        periodos.append((atual, fim_periodo))
        atual = proximo
    return periodos


def processar_nf(sf_conn, tipo):
    """tipo: 'ENTRADA' ou 'SAIDA'"""
    api_name = f'NF_{tipo}'
    nome = f'NF_{tipo}_SILT_RAW'
    tabela = f'DRE_AGENTE_ALL.BRONZE.{nome}'
    stage = f'@DRE_AGENTE_ALL.BRONZE.STG_LANDING/nf_{tipo.lower()}_silt/'
    endpoint = f'/armazem/movimentacoes/nota-fiscal-{"entrada" if tipo == "ENTRADA" else "saida"}'
    dt_inicio = datetime.datetime.now()

    log(f'=== {nome} (incremental) ===')
    try:
        # Buscar ultima data carregada
        ultima_data = get_ultima_data(sf_conn, api_name)
        hoje = datetime.date.today()

        if MODO_TESTE:
            ultima_data = hoje - datetime.timedelta(days=7)
            log(f'MODO TESTE: buscando apenas ultimos 7 dias')

        # Se periodo > 31 dias, quebra em meses
        if (hoje - ultima_data).days > 31:
            periodos = gerar_periodos_mensais(ultima_data, hoje)
            log(f'Periodo total: {ultima_data} a {hoje} ({len(periodos)} meses)')
        else:
            periodos = [(ultima_data, hoje)]
            log(f'Periodo: {ultima_data} a {hoje}')

        # Deleta registros do periodo completo para evitar duplicatas
        sf_cur = sf_conn.cursor()
        sf_cur.execute(f"DELETE FROM {tabela} WHERE DATA_CADASTRO >= '{ultima_data}'")
        qt_deletados = sf_cur.fetchone()[0]
        log(f'Deletados: {qt_deletados} registros do periodo')

        qt_total = 0
        total_registros_api = 0

        for i, (dt_de, dt_ate) in enumerate(periodos, 1):
            log(f'--- Mes {i}/{len(periodos)}: {dt_de} a {dt_ate} ---')

            # Delay entre chamadas para evitar rate limiting
            if i > 1:
                time.sleep(15)

            params = {
                'inicioDataCadastro': str(dt_de),
                'finalDataCadastro': str(dt_ate)
            }
            dados = chamar_api(endpoint, params)

            if not dados:
                log(f'Nenhum dado para {dt_de} a {dt_ate}')
                continue

            total_registros_api += len(dados)
            arquivo = salvar_csv(dados, COLUNAS_NF, f'nf_{tipo.lower()}_silt_{i}.csv')
            qt = carregar_snowflake(sf_conn, arquivo, tabela, stage, len(COLUNAS_NF), COLUNAS_NF, truncar=False)
            qt_total += qt

        # Atualiza controle
        set_ultima_data(sf_conn, api_name, str(hoje))

        ds_filtro = f'{ultima_data} a {hoje} ({len(periodos)} meses)'
        dt_fim = datetime.datetime.now()
        registrar_log(sf_conn, tabela, 'incremental', dt_inicio, dt_fim, total_registros_api, qt_deletados, qt_total, 'SUCESSO', None, ds_filtro)
        log(f'{nome} concluido: {qt_total} registros totais')
        return qt_total

    except Exception as e:
        dt_fim = datetime.datetime.now()
        log(f'ERRO: {e}')
        ds_filtro = f'{ultima_data} a {hoje}' if 'ultima_data' in dir() else None
        registrar_log(sf_conn, tabela, 'incremental', dt_inicio, dt_fim, 0, 0, 0, 'ERRO', str(e)[:500], ds_filtro)
        raise


if __name__ == '__main__':
    log('=== INICIO ETL SILT APIs -> SNOWFLAKE ===')
    if MODO_TESTE:
        log('*** MODO TESTE ATIVADO - dados reduzidos ***')

    # Argumento opcional: python etl_silt.py --apenas=nf_entrada
    apenas = None
    for arg in sys.argv:
        if arg.startswith('--apenas='):
            apenas = arg.split('=')[1].upper()

    sf_conn = conectar_snowflake()
    try:
        total = 0
        # SALDO_ESTOQUE desabilitado ate resolver timeout com equipe SILT
        if apenas == 'SALDO_ESTOQUE':
            total += processar_saldo_estoque(sf_conn)
        if apenas is None or apenas == 'NF_ENTRADA':
            total += processar_nf(sf_conn, 'ENTRADA')
        if apenas is None or apenas == 'NF_SAIDA':
            total += processar_nf(sf_conn, 'SAIDA')
        log(f'=== ETL SILT CONCLUIDO: {total} registros totais ===')
    except Exception as e:
        log(f'ERRO GERAL: {e}')
    finally:
        sf_conn.close()
