# Migração Cross-Subscription — Spend Analysis v2

**Data:** 2026-04-16
**Status:** 🔴 **BLOQUEADO** — tentativa em 2026-04-17 abortada, ver "Histórico" ao final
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

**Estado atual (pós-revert):**
- Function App `az-pg-spend-analysis-ai-agent` rodando em Flex Consumption no RG `azpgspendanalysisaiagent` (subscription origem)
- Frontend `salmon-beach-05662180f.6.azurestaticapps.net` HTTP 200
- Health endpoint HTTP 200
- CORS, file share mount `models-data`, HTTPS-only, todas as 15 app settings restauradas do backup em `/tmp/funcapp-backup/`
- Migração cross-subscription **pausada indefinidamente**
