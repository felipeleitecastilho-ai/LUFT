# Licoes Aprendidas - Projeto Luft Logistics
> Para uso interno Keyrus (Felipe + CoCo) em futuros projetos

---

## 1. Snowflake - Cortex Agent

### Sintaxe correta para criar agente:
```sql
CREATE OR REPLACE AGENT schema.nome
  COMMENT = '...'
  PROFILE = '{"display_name":"...", "avatar":"..."}'
  FROM SPECIFICATION
  $$
  -- YAML aqui (nao JSON)
  models:
    orchestration: auto
  tools:
    - tool_spec:
        type: "cortex_analyst_text_to_sql"
        name: "NomeFerramenta"
  tool_resources:
    NomeFerramenta:
      semantic_view: "DB.SCHEMA.SEMANTIC_VIEW"
  $$;
```
- **YAML obrigatorio** (JSON nao persiste a spec)
- `spec = '...'` NAO funciona
- `SPECIFICATION = $$...$$` NAO funciona
- Sempre verificar com DESCRIBE AGENT se agent_spec esta preenchido

### Semantic View - aliases:
- O alias AS deve ser UNICO (nao repetir nomes entre facts e dimensions)
- Se o alias conflita com nome de coluna na view, usar o nome original da coluna

### Agente - evitar alucinacao:
- NUNCA ter duas ferramentas com dados sobrepostos
- Se trocar fonte, SUBSTITUIR a ferramenta (nao adicionar segunda)
- Roteamento claro nas instructions (qual pergunta vai pra qual ferramenta)

### Grants apos CREATE OR REPLACE:
- CREATE OR REPLACE perde os GRANTs existentes
- Sempre re-aplicar GRANT USAGE apos recriar o agente
- Future grants NAO se aplicam a agentes (somente views, tables, semantic views)

---

## 2. ETL - Padroes que funcionaram

### Quebra automatica por volume:
- < 50k registros: fetchall direto
- 50k - 500k: fetchmany em lotes (Protheus)
- 500k - 1M: OFFSET/FETCH em lotes (TMS)
- > 1M: filtrar por data (janela 7/90 dias) ou mes a mes (SILT)

### Modos de carga:
- `full`: TRUNCATE + reload (views de status/snapshot)
- `incremental`: DELETE >= ultima_data - 2 dias + insere novos
- `incremental_N`: janela deslizante de N dias (GPS, telemetria)

### API com rate limiting:
- 15s delay entre chamadas
- Retry 3x com backoff (30s, 60s, 90s)
- Mes a mes para periodos grandes (>31 dias)

### SQL Server - armadilhas:
- Colunas com caracteres especiais (parenteses, espacos) quebram DDL no Snowflake
- Sempre sanitizar nomes: `re.sub(r'[^A-Z0-9_]', '', col)`
- INFORMATION_SCHEMA.COLUMNS para views retorna as colunas corretas
- OFFSET/FETCH precisa de ORDER BY (usar `ORDER BY (SELECT NULL)` se nao importa ordem)

### Formatos de data - VERIFICAR ANTES:
- Protheus Oracle: YYYYMMDD (nao DD/MM/YYYY)
- SILT API: ISO (YYYY-MM-DD)
- CSVs manuais: DD/MM/YYYY ou D/M/YYYY (inconsistente)
- SQL Server: datetime nativo

### Controle centralizado (ETL_CONTROL):
- Uma linha por fonte/tabela incremental
- Campos: API_NAME, ULTIMA_DATA_CARGA, UPDATED_AT
- Melhor que arquivo local (last_run.txt) - visivel por todos

---

## 3. PowerShell (CoCo no Windows)

### Nao funciona:
- Heredoc `<<'EOF'` (sintaxe bash)
- `&&` para encadear comandos (usar `;`)
- Aspas simples dentro de aspas simples em one-liners
- Comandos python multi-linha com aspas mistas

### Funciona:
- `Set-Content -Path "arquivo" -Value @'...'@` para criar arquivos
- `;` para encadear comandos
- `Remove-Item` para apagar
- `Move-Item` para mover
- Git commit com aspas simples para mensagem multi-linha

---

## 4. Comunicacao com o usuario

### O que deu certo:
- Mostrar plano ANTES de implementar (usuario aprova)
- Backup ANTES de alterar (cria confianca)
- Testar com queries ANTES de dizer "pronto"
- Pendencias atualizadas a cada sessao (visibilidade)
- Mensagens prontas para Alynne (economiza tempo do usuario)

### O que melhorar:
- Perguntar formato de dados ANTES de assumir (datas, valores)
- Verificar volume da tabela ANTES de fazer SELECT * (287M!)
- Confirmar se usuario quer commit antes de fazer
- Nao criar arquivos auxiliares sem avisar (test_tms.py, ver_colunas.py)

### Fluxo ideal para nova fonte de dados:
1. Listar tabelas/colunas disponiveis
2. Usuario escolhe quais quer
3. Verificar volume e formato de datas
4. Definir modo (full/incremental) por tabela
5. Implementar script + tabelas Bronze
6. Testar com --apenas=UMA_TABELA
7. Rodar completo
8. Confirmar com usuario

---

## 5. Organizacao de projeto

### Estrutura de pastas:
```
PROJETO/
├── scripts_etl/    → Python + bat + chaves
├── docs/           → Documentacao + prototipos
├── dados_csv/      → Fontes CSV
├── backups/        → Backups SQL/specs
├── streamlit/      → Apps Streamlit
└── .gitignore      → Ignorar: chaves, backups, temp
```

### .gitignore essencial:
```
*.p8
backup_*
temp/
__pycache__/
*.pyc
```

### Commits - padrao:
- Um commit por entrega logica (nao por arquivo)
- Mensagem em portugues (projeto BR)
- Nao commitar arquivos auxiliares de debug

---

## 6. Setup Inicial de Projeto (fazer PRIMEIRO)

### Ao iniciar qualquer projeto novo:
1. Criar pasta no repositorio Git
2. Criar .gitignore imediatamente:
```
# Credenciais
*.p8
*.pem
*.key
snowflake_key*
credentials*
.env

# Backups e temp
backup_*
temp/
__pycache__/
*.pyc

# Dados grandes
*.csv
*.xlsx
*.gz

# OS
.DS_Store
Thumbs.db
```
3. Criar estrutura de pastas:
```
PROJETO/
├── scripts_etl/
├── docs/
├── streamlit/
├── dados_csv/
├── backups/
└── .gitignore
```
4. Fazer commit inicial: `git init && git add .gitignore && git commit -m "Initial commit"`
5. Criar repositorio remoto e fazer push

### Regras de Git durante o projeto:
- **SEMPRE perguntar antes de commitar** (nunca fazer commit automatico)
- **SEMPRE perguntar antes de push** (usuario pode querer revisar)
- **Nunca commitar arquivos auxiliares de debug** (test_*.py, ver_*.py)
- **Nunca commitar credenciais** (.p8, .env, passwords)
- **Um commit por entrega logica** (nao por arquivo individual)
- **Mensagem em portugues** se projeto BR
- **Organizar pastas ANTES do commit final** (nao deixar bagunca no repo)

### Regras de seguranca (Snowflake):
- **SEMPRE fazer backup antes de DROP ou ALTER** (salvar DDL em arquivo local)
- **SEMPRE fazer backup antes de CREATE OR REPLACE** (perde grants e versoes)
- Salvar com: `SELECT GET_DDL('objeto', 'nome')` ou `DESCRIBE`
- Formato do backup: `backup_<objeto>_<YYYYMMDD>.txt`

---

## 7. Padroes de nomenclatura (seguir em todos os projetos)

### Tabelas:
- Bronze: `<NOME>_<FONTE>_RAW` (ex: COMPRAS_PROTHEUS_RAW, NF_ENTRADA_SILT_RAW)
- Silver: `<NOME>` sem sufixo (ex: COMPRAS_CONTABIL, RAZAO, ABASTECIMENTOS)
- Gold: `VW_SEMANTICA_<NOME>` para views, `DT_<NOME>` para Dynamic Tables, `SEMANTICO_<NOME>` para Semantic Views

### Colunas (prefixos padrao):
| Prefixo | Significado | Exemplo |
|---|---|---|
| CD_ | Codigo | CD_FILIAL, CD_PRODUTO |
| NM_ | Nome | NM_FILIAL, NM_FORNECEDOR |
| DS_ | Descricao | DS_CATEGORIA, DS_STATUS |
| VL_ | Valor monetario | VL_TOTAL, VL_FRETE |
| QT_ | Quantidade | QT_LITROS, QT_KM |
| DT_ | Data | DT_EMISSAO, DT_CARGA |
| DH_ | Data+hora | DH_CARGA |
| FL_ | Flag (booleano) | FL_ATIVO, FL_RATEIO |
| PCT_ | Percentual | PCT_MARGEM, PCT_OCUPACAO |

### Colunas na Gold (nomes amigaveis):
- Remover prefixos: NM_FILIAL → FILIAL
- Nomes que o usuario entende: VL_TOTAL → VALOR_TOTAL
- Sem abreviacoes: DS_CTR → DESCRICAO_CONTRATO

### Dynamic Tables Silver:
- Sempre `lag = 'DOWNSTREAM'`
- Sempre `warehouse = COMPUTE_WH`
- Sempre `refresh_mode = 'AUTO'`
- Converter tipos: TRY_TO_DATE, TRY_CAST
- TRIM em todos os campos texto
- Adicionar ANO e MES derivados da data principal

### Semantic Views:
- Facts = campos numericos (SUM, AVG, MIN, MAX)
- Dimensions = campos de filtro/agrupamento
- COMMENT em todos os campos (guia o agente)
- SAMPLE_VALUES nos campos mais importantes
- Alias AS deve ser o mesmo nome da coluna (evitar conflitos)

---

## 8. Monitoramento padrao (criar em todo projeto)

### Tabela ETL_CONTROL (controle de datas):
```sql
CREATE TABLE BRONZE.ETL_CONTROL (
    API_NAME VARCHAR,
    ULTIMA_DATA_CARGA DATE,
    UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```
- Uma linha por fonte incremental
- ETL consulta antes de rodar (sabe de onde comecar)
- ETL atualiza apos sucesso

### Tabela ETL_LOG (historico de execucoes):
```sql
CREATE TABLE BRONZE.ETL_LOG (
    ID_EXECUCAO NUMBER AUTOINCREMENT,
    DT_INICIO TIMESTAMP_NTZ,
    DT_FIM TIMESTAMP_NTZ,
    NM_TABELA VARCHAR,
    DS_MODO VARCHAR,
    QT_EXTRAIDOS NUMBER,
    QT_DELETADOS NUMBER,
    QT_CARREGADOS NUMBER,
    QT_TOTAL_TABELA NUMBER,
    DS_STATUS VARCHAR,
    DS_ERRO VARCHAR,
    DS_FILTRO VARCHAR,
    QT_DURACAO_SEG NUMBER
);
```
- Todo script insere uma linha ao finalizar (sucesso ou erro)
- Permite auditoria completa
- Alimenta o painel Streamlit e alertas

### Alertas por email (criar sempre):
- Alerta 1: resumo diario (07:00) - quantos registros carregou
- Alerta 2: falhas (08:00) - dispara se algum ETL teve erro
- Usar SNOWFLAKE ALERT com NOTIFICATION INTEGRATION

### Painel Streamlit (criar sempre):
- Cards de status por fonte (ok/erro/atrasado)
- Tabela com historico de cargas (ultimos 7 dias)
- Filtro por fonte (Protheus, SILT, TMS, etc.)
- Destaque vermelho para erros
- Deploy via stage: `@BRONZE.STG_LANDING/streamlit/app.py`

### Por que fazer isso em todo projeto:
- Cliente ve que o ETL esta funcionando sem precisar perguntar
- Erros sao detectados no mesmo dia (nao semanas depois)
- Facilita troubleshooting (sabe exatamente onde falhou)
- Historico de volume ajuda a prever crescimento
- Demonstra profissionalismo na entrega

---

## 9. Checklist novo projeto Snowflake + Agent

- [ ] Definir fontes de dados e volumes
- [ ] Criar database + schemas (BRONZE, SILVER, GOLD)
- [ ] Criar roles (ADMIN, VIEWER, ETL service account)
- [ ] Configurar future grants nas 3 camadas
- [ ] Criar Key Pair para service account
- [ ] Implementar ETL Bronze (script por fonte)
- [ ] Criar Dynamic Tables Silver (tipagem)
- [ ] Criar Views Gold (nomes amigaveis, JOINs)
- [ ] Criar Semantic Views (facts + dimensions)
- [ ] Criar Agente (FROM SPECIFICATION $$ YAML $$)
- [ ] Testar agente com perguntas do usuario
- [ ] Configurar alertas (email falhas)
- [ ] Criar painel monitoramento (Streamlit)
- [ ] Agendar ETL (Task Scheduler / cron)
- [ ] Documentar e fazer KT
