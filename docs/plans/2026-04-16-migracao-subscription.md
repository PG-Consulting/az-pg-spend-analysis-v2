# Migração Cross-Subscription — Spend Analysis → Spend.AI

**Data:** 2026-04-16 (início) / 2026-04-17 (rebuild)
**Status:** 🟡 **AGUARDANDO ADMIN ENTRA ID** — infra nova 100% pronta, bloqueada em 1 ação de 2 min
**Pré-requisito:** ✅ Contributor em escopo subscription `556bd4bb-622a-435e-82bf-700980248f94` confirmado

## Objetivo

Mover todos os recursos ativos para a subscription do cliente (`CopilotPG`). URL default do SWA (`salmon-beach-05662180f.6.azurestaticapps.net`) é preservada no `az resource move`. Custom domain fica como plano futuro.

## Identidades

| | Valor |
|---|---|
| Subscription destino | `556bd4bb-622a-435e-82bf-700980248f94` |
| RG destino | `CopilotPG` |
| Tenant (ambas) | `f5e3f799-605a-4c12-9c43-859706522b40` |
| Usuário executor | `victor.juliani@procurementgarage.com` |

App Registration MSAL é tenant-level — não migra.

## Recursos a mover (5)

| Recurso | Tipo |
|---|---|
| `az-pg-spend-analysis-ai-agent` | Function App |
| `az-pg-spend-analysis-static-app` | Static Web App (salmon-beach) |
| `azpgspendanalysisaiagent` | Storage Account |
| `FLEX-az-pg-spend-analysis-ai-agent-1929` | App Service Plan |
| `azpgspendanalysisaiagent` | Application Insights |

## Recursos a NÃO migrar (excluir na limpeza)

- `app-pg-spend-analysis-ai-agent` (SWA antigo, green-pebble-0c11ffc0f)
- `openai-pg-spend-analysis` (Cognitive Services não usado)
- `vault865` (Recovery Services Vault)
- `edf75407-...-dashboard` (Portal Dashboard)
- RG `azpgspendanalysis` inteiro (legado v1)

## Sequência de execução (janela noturna)

### 1. Registrar 3 providers na destino
```bash
az provider register --namespace Microsoft.Storage --subscription 556bd4bb-622a-435e-82bf-700980248f94
az provider register --namespace Microsoft.Insights --subscription 556bd4bb-622a-435e-82bf-700980248f94
az provider register --namespace Microsoft.OperationalInsights --subscription 556bd4bb-622a-435e-82bf-700980248f94
```
Aguardar todos virarem `Registered`:
```bash
az provider list --subscription 556bd4bb-622a-435e-82bf-700980248f94 \
  --query "[?namespace=='Microsoft.Storage' || namespace=='Microsoft.Insights' || namespace=='Microsoft.OperationalInsights'].{ns:namespace, state:registrationState}" -o table
```

### 2. Coletar resource IDs da origem
```bash
az resource list --resource-group azpgspendanalysisaiagent \
  --query "[?name=='az-pg-spend-analysis-ai-agent' || name=='az-pg-spend-analysis-static-app' || name=='azpgspendanalysisaiagent' || name=='FLEX-az-pg-spend-analysis-ai-agent-1929'].id" -o tsv
```

### 3. Checar locks no RG origem
```bash
az lock list --resource-group azpgspendanalysisaiagent -o table
```
Se houver, remover antes do move.

### 4. Pausar uploads de jobs
Comunicar ao time que sistema ficará indisponível por alguns minutos. Idealmente fila `taxonomy-jobs` vazia (sem jobs em `PROCESSING`).

### 5. Dry-run `validateMoveResources`
```bash
az resource invoke-action \
  --action validateMoveResources \
  --ids "/subscriptions/<origem>/resourceGroups/azpgspendanalysisaiagent" \
  --request-body '{"resources":["<id1>","<id2>",...], "targetResourceGroup":"/subscriptions/556bd4bb-622a-435e-82bf-700980248f94/resourceGroups/CopilotPG"}'
```
Se retornar erro, corrigir antes de seguir.

### 6. Executar o move ⚠️ ponto de não-retorno
```bash
az resource move \
  --destination-subscription-id 556bd4bb-622a-435e-82bf-700980248f94 \
  --destination-group CopilotPG \
  --ids <id1> <id2> <id3> <id4> <id5>
```
Downtime esperado: minutos.

### 7. Validação pós-move
- Frontend carrega em `salmon-beach-05662180f.6.azurestaticapps.net`
- Login MSAL funciona
- Submit de job no frontend
- Worker processa até `CLASSIFIED`
- Telemetria chegando no Application Insights

### 8. Re-config
- Validar GitHub Actions secret `AZURE_STATIC_WEB_APPS_API_TOKEN` (pode precisar regerar)
- Atualizar docs: `CLAUDE.md`, `DEPLOYMENT.md` (se houver referência a subscription ID)
- `local.settings.json` / `.env.local` — só dev local, baixa prioridade

### 9. Limpeza na origem
Excluir:
- RG `azpgspendanalysis` (legado v1)
- SWA antigo `app-pg-spend-analysis-ai-agent`
- `openai-pg-spend-analysis`
- `vault865`
- Portal dashboard `edf75407-...`

### 10. (Opcional futuro)
- Flex → Consumption Y1 conforme `docs/migracao-consumption.md`
- Configurar custom domain no SWA

## Riscos e cuidados

- **Downtime**: minutos, não-zero
- **Deploy token SWA**: pode regerar após move — atualizar GitHub secret
- **Jobs em PROCESSING**: se houver durante o move, podem ir para ERROR — cleanup timer recupera PENDING órfãos
- **Storage**: File Share `models-data` e queues preservados (dado interno ao Storage Account)
- **Rollback**: `az resource move` não tem rollback automático. Em caso de falha na validação pós-move, abrir ticket Azure Support.

## Histórico — Tentativa 2026-04-17

**Resultado:** Migração abortada. Sistema restaurado para Flex Consumption na subscription origem.

**O que foi feito:**
1. ✅ Contributor atribuído na subscription destino
2. ✅ Providers `Microsoft.Storage`, `Microsoft.Insights`, `Microsoft.OperationalInsights` registrados
3. ✅ Lock `AzureBackupProtectionLock` removido (desregistrado Storage do vault865 — backup history do File Share perdida, ~30 snapshots)
4. ❌ `validateMoveResources` falhou 2x com `ResourceMoveTimedOut` em `Microsoft.Web/serverFarms` (timeout fixo 15min insuficiente para Flex Consumption)
5. ❌ `az resource move` direto também falhou com o mesmo timeout
6. **Tentativa de swap Flex→Y1 como workaround** — criado Y1, deploy ok, mas host entrou em Error por `functionTimeout: 00:30:00` do host.json ser incompatível com limite HARD de 10min do Y1 Consumption
7. ✅ **Revert** — Y1 deletado, Flex Consumption recriado (novo plan: `ASP-azpgspendanalysisaiagent-a68a`), deploy ok, `/api/health` HTTP 200

**Aprendizados críticos:**
- **Flex Consumption não suporta cross-subscription move estável** — timeout de 15min no provider Web consistentemente insuficiente
- **Y1 Consumption não é viável** como substituto direto — limite HARD de 10min por invocação, incompatível com `functionTimeout: 30min` do worker de classificação (chunks de 500 items via múltiplas chamadas Grok)
- Registro de providers e move são **operações separadas** — providers continuam registrados mesmo sem o move acontecer

**Caminhos possíveis para retomar:**

| Opção | Descrição | Esforço | Custo/mês |
|---|---|---|---|
| A | Refactor worker: reduzir CHUNK_SIZE de 500 para ~100-150 + Y1 + move | Alto (código + testes + staging) | ~R$0 |
| B | App Service B1 em vez de Flex/Y1 + move (B1 suporta move + timeout ilimitado) | Médio (setup + deploy + move) | ~R$50 |
| C | EP1 Elastic Premium + move | Médio | ~R$200+ |
| D | Aguardar fix do Microsoft Flex move (sem timeline) | — | ~R$42 atual |

**Recomendação**: quando retomar, avaliar **Opção B** (App Service B1) — suporta move sem timeout, always-on elimina cold start, custo comparável ao Flex atual. Ou **Opção A** se time de dev tiver bandwidth para refactor.

**Estado após revert (intermediário):**
- Function App `az-pg-spend-analysis-ai-agent` rodando em Flex Consumption no RG `azpgspendanalysisaiagent` (subscription origem)
- Sistema operacional, nada quebrado
- Decisão: partir para **Caminho 1 — rebuild completo** em CopilotPG com rebrand Spend.AI

## Execução 2026-04-17 (parte 2) — Rebuild Spend.AI em CopilotPG

**Padrão de nomenclatura**: `pg-ai-pi-{solução}-{papel}` (Storage sem hífens: `pgaipispendai`)

### Recursos criados em `CopilotPG` / subscription `556bd4bb-...`

| Recurso | Nome | Detalhes |
|---|---|---|
| Storage Account | `pgaipispendai` | Standard_LRS, StorageV2, Brazil South, HTTPS-only, TLS 1.2, blob public OFF |
| File Share | `models-data` | 5120 GB quota, 375 arquivos + 100 pastas + 257MB migrados via AzCopy (0 falhas) |
| Queue | `taxonomy-jobs` + `taxonomy-jobs-poison` | Vazias (novo sistema começa limpo) |
| Log Analytics | `pg-ai-pi-spendai-logs` | 30 dias retenção |
| App Insights | `pg-ai-pi-spendai-insights` | Workspace-based (InstrumentationKey: `bc9ad1f2-e879-4fe2-9c00-0e201b75621e`) |
| Function App | `pg-ai-pi-spendai-api` | Flex Consumption, Python 3.11, Functions v4, auto-criou plan `ASP-CopilotPG-...` |
| Static Web App | `pg-ai-pi-spendai-app` | Free tier, East US 2 (região única disponível p/ Free) |

### URLs novas
- **Frontend**: `https://salmon-meadow-00d2bba0f.7.azurestaticapps.net`
- **Backend**: `https://pg-ai-pi-spendai-api.azurewebsites.net`

### Configuração aplicada no Function App destino
- 14 app settings restauradas do backup `/tmp/funcapp-backup/` (pulando AzureWebJobsStorage, DEPLOYMENT_STORAGE_CONNECTION_STRING, APPLICATIONINSIGHTS_CONNECTION_STRING — auto-criadas apontando pra novo Storage/Insights)
- APPINSIGHTS_INSTRUMENTATIONKEY atualizado para valor da nova App Insights
- ALLOWED_ORIGINS = `https://salmon-meadow-00d2bba0f.7.azurestaticapps.net` (SWA novo)
- CORS allowedOrigins = `https://salmon-meadow-00d2bba0f.7.azurestaticapps.net` + supportCredentials: true
- File Share mount `/mount/models` → `models-data` (state: Ok)
- HTTPS-only: true
- Deploy via `func azure functionapp publish pg-ai-pi-spendai-api` — sucesso
- `/api/health` → HTTP 200, `{"status": "healthy", "version": "3.0"}`

### Alterações no repo (commitadas em `ea022b0` na main)
- `.github/workflows/azure-static-web-apps.yml`:
  - Secret renomeada: `AZURE_STATIC_WEB_APPS_API_TOKEN_SALMON_BEACH_05662180F` → `AZURE_STATIC_WEB_APPS_API_TOKEN_SALMON_MEADOW_00D2BBA0F`
  - `NEXT_PUBLIC_API_URL`: `az-pg-spend-analysis-ai-agent.azurewebsites.net/api` → `pg-ai-pi-spendai-api.azurewebsites.net/api`
- `docs/plans/2026-04-16-migracao-subscription.md` (este arquivo) — histórico atualizado

### GitHub Actions
- Secret antigo `AZURE_STATIC_WEB_APPS_API_TOKEN_SALMON_BEACH_05662180F` ainda existe (não foi deletado — deletar só após go-live confirmado)
- Secret novo `AZURE_STATIC_WEB_APPS_API_TOKEN_SALMON_MEADOW_00D2BBA0F` criado via `gh secret set`
- Push para main disparou workflow run `24588980672` — **success** (build + deploy SWA novo)

### Smoke tests automatizados (OK)
- Frontend HTTP 200
- Backend `/api/health` HTTP 200
- CORS preflight OPTIONS → 204 com headers corretos
- File Share counts batem com origem: `sectors` (2), `projects` (3)

## 🛑 Bloqueio atual — Redirect URI no Entra ID

**Tentativa de login MSAL falhou** com:
```
AADSTS50011: The redirect URI 'https://salmon-meadow-00d2bba0f.7.azurestaticapps.net'
does not match the redirect URIs configured for the application '09ed8a33-cc9e-446c-8db5-e4ca0955650f'
```

**Causa**: App Registration `PG Spend AI` (tenant ProcurementGarage, `f5e3f799-...`) tem apenas a URL do SWA antigo (`salmon-beach-...`) cadastrada. Precisa adicionar a nova.

**Usuário Victor não tem permissão pra editar o App Registration** — precisa ser o mesmo admin que seguiu o `docs/guia-ativacao-autenticacao.html` em 2026-03-23 (via **entra.microsoft.com**, não portal.azure.com).

**Instruções pro admin** (enviar por email/slack):
```
Acesse entra.microsoft.com
Menu lateral: Identidade → Aplicativos → Registros de aplicativo
Abra "Spend Analysis v3" (displayName técnico: "PG Spend AI")
Gerenciar → Autenticação
Na seção "Aplicativo de página única", clicar "Adicionar URI"
Colar: https://salmon-meadow-00d2bba0f.7.azurestaticapps.net
Salvar

(É additive — a URL antiga salmon-beach-... fica, as duas convivem)
```

## Próximos passos (após admin adicionar a URI)

1. **Validação manual pelo usuário** — acessar URL nova, login MSAL, ver se 3 projetos aparecem, submeter job de teste, worker processa até CLASSIFIED
2. **Go-live** — comunicar URL nova ao time (consultores)
3. **Cleanup origem** (TASK 17):
   - Deletar RG inteiro `azpgspendanalysisaiagent` (Function App + ASP Flex + Storage + Insights + SWA antigo + vault865 + dashboard)
   - Deletar `openai-pg-spend-analysis` (não usado)
   - Deletar RG legado `azpgspendanalysis` (v1)
   - Deletar secret antigo `AZURE_STATIC_WEB_APPS_API_TOKEN_SALMON_BEACH_05662180F` do GitHub
4. **Atualizar docs**:
   - `CLAUDE.md` — URLs, nomes, subscription
   - `docs/guia-ativacao-autenticacao.html` — URL nova no passo 1
   - Remover URL antiga do App Registration (após SWA antigo deletado)
5. **Opcional**: configurar custom domain no SWA novo (ex: `spend.procurementgarage.com`)

## Fallback seguro

Origem (subscription `aa2dae69-...`) **NÃO foi apagada**. Sistema continua funcional em `salmon-beach-05662180f.6.azurestaticapps.net` até decisão de cutover.
