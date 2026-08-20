import oracledb

conn = oracledb.connect(user='consulta', password='pvcqh92861VCPME@!', dsn='201.157.213.136:1521/C1JTKS_192934_P')
cur = conn.cursor()

for v in ['DATALAKE_EMPRESAS', 'DATALAKE_FORNECEDOR', 'DATALAKE_PRODUTOS']:
    cur.execute(f'SELECT * FROM U_C1JTKS_PR.{v} WHERE ROWNUM=1')
    cols = [c[0] for c in cur.description]
    cur.execute(f'SELECT COUNT(*) FROM U_C1JTKS_PR.{v}')
    total = cur.fetchone()[0]
    print(f'{v} ({total} registros, {len(cols)} colunas):')
    print(f'  {cols}')
    print()

conn.close()
