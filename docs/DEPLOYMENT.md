# Deployment — Spend Analysis v3

## Infraestrutura Azure

| Recurso | Nome |
|---------|------|
| Function App | `az-pg-spend-analysis-ai-agent` (ou novo para v3) |
| Resource Group | `azpgspendanalysisaiagent` |
| Storage Account | `azpgspendanalysisaiagent` |
| File Share | `models-data` (montado em `/mount/models`) |
| Static Web Apps | Deploy automático via GitHub Actions |

---

## CI/CD

Push para `main` dispara deploy automático:

- **Frontend** → Azure Static Web Apps (build Next.js com `output: 'export'`)
- **Backend** → deploy separado via `func azure functionapp publish`

O workflow está em `.github/workflows/azure-static-web-apps.yml`.

---

## Deploy do Backend

```bash
# Autenticar no Azure
az login

# Publicar Function App
func azure functionapp publish az-pg-spend-analysis-ai-agent --python

# Verificar logs
func azure functionapp logstream az-pg-spend-analysis-ai-agent
```

### Variáveis de Ambiente no Azure

Configurar via Portal Azure ou CLI:

```bash
az functionapp config appsettings set \
  --name az-pg-spend-analysis-ai-agent \
  --resource-group azpgspendanalysisaiagent \
  --settings \
    GROK_API_KEY="xai-..." \
    DIRECT_LINE_SECRET="..." \
    MODELS_DIR_PATH="/mount/models"
```

---

## File Share (Persistência)

O diretório `models/` é montado como Azure File Share em `/mount/models`. Inclui:

- `sectors/` — configs de setores
- `projects/` — configs e KBs dos projetos
- `taxonomy_jobs/` — fila de jobs async
- `varejo/`, `educacional/` — modelos ML legados

### Copiar Models para o File Share (primeiro deploy)

```bash
# Listar conteúdo do File Share
az storage file list \
  --share-name models-data \
  --account-name azpgspendanalysisaiagent \
  --output table

# Upload de um diretório
az storage file upload-batch \
  --source ./models \
  --destination models-data \
  --account-name azpgspendanalysisaiagent
```

---

## Operações de Manutenção

### Verificar Jobs em Execução

```bash
# Listar jobs
az storage file list \
  --share-name models-data \
  --path "taxonomy_jobs" \
  --account-name azpgspendanalysisaiagent \
  --output table

# Ver status de um job específico
az storage file download \
  --share-name models-data \
  --path "taxonomy_jobs/{JOB_ID}/status.json" \
  --dest /tmp/status.json \
  --account-name azpgspendanalysisaiagent \
  --no-progress && cat /tmp/status.json
```

### Forçar Job para ERROR (emergência)

O worker faz auto-limpeza de jobs `PROCESSING` com mais de 1 hora automaticamente. Para casos urgentes:

```bash
# 1. Baixar status.json
az storage file download \
  --share-name models-data \
  --path "taxonomy_jobs/{JOB_ID}/status.json" \
  --dest /tmp/status.json \
  --account-name azpgspendanalysisaiagent

# 2. Editar: mudar "status": "PROCESSING" para "status": "ERROR"
jq '.status = "ERROR" | .error = "Forçado manualmente"' /tmp/status.json > /tmp/status_error.json

# 3. Fazer upload de volta
az storage file upload \
  --share-name models-data \
  --source /tmp/status_error.json \
  --path "taxonomy_jobs/{JOB_ID}/status.json" \
  --account-name azpgspendanalysisaiagent
```

### Reiniciar Function App

```bash
# Mata todos os workers em execução
az functionapp restart \
  --name az-pg-spend-analysis-ai-agent \
  --resource-group azpgspendanalysisaiagent
```

---

## Deploy do Frontend

O build é estático (`next.config.js` com `output: 'export'`). A pipeline CI/CD do GitHub Actions faz o deploy automaticamente para o Azure Static Web Apps.

Para deploy manual:

```bash
cd frontend
npm run build   # gera ./out/
# Fazer upload de ./out/ para o Static Web App via Azure CLI ou portal
```

### Variáveis de Ambiente do Frontend

Configurar no Azure Static Web Apps → Configuration:

```
NEXT_PUBLIC_API_URL=https://az-pg-spend-analysis-ai-agent.azurewebsites.net/api
NEXT_PUBLIC_FUNCTION_KEY=   # se aplicável
```

---

## Configuração do Azurite (Desenvolvimento Local)

O Azurite emula o Azure Storage localmente. Necessário para o Azure Functions rodar com `AzureWebJobsStorage=UseDevelopmentStorage=true`.

```bash
# Instalar
npm install -g azurite

# Rodar (na raiz do projeto)
azurite --location AzuriteConfig --silent

# O diretório AzuriteConfig/ armazena os dados locais do emulador
# Já está no .gitignore
```

---

## Checklist de Primeiro Deploy

- [ ] File Share `models-data` criado na Storage Account
- [ ] Modelos ML legados (`varejo/`, `educacional/`) copiados para o File Share
- [ ] `Spend_Taxonomy.xlsx` presente em `data/taxonomy/` no pacote deploy
- [ ] Variáveis de ambiente configuradas no Function App
- [ ] Function App com timeout de 30 minutos (`host.json` já configurado)
- [ ] CORS configurado (ou `*` para desenvolvimento)
- [ ] Frontend: `NEXT_PUBLIC_API_URL` apontando para o backend correto
- [ ] Testar `GET /api/ListSectors` retornando `{ "sectors": [] }`
- [ ] Criar setor e projeto via API ou frontend
- [ ] Testar upload de arquivo pequeno (100 linhas) end-to-end

---

## Monitoramento

- **Logs em tempo real**: `func azure functionapp logstream az-pg-spend-analysis-ai-agent`
- **Application Insights**: configurar `APPLICATIONINSIGHTS_CONNECTION_STRING` para métricas e traces
- **Jobs em erro**: verificar `taxonomy_jobs/*/status.json` com `"status": "ERROR"`
- **Timeout do worker**: budget de 20 minutos por ciclo. Se um job demora mais de 20min/ciclo, verificar tamanho dos chunks e número de workers LLM
