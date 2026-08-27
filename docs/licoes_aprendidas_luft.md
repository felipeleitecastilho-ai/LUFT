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

## 6. Checklist novo projeto Snowflake + Agent

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
