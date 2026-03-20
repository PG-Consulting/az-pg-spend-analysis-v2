# Migração Azure Functions: Flex Consumption → Consumption

**Data:** 2026-03-03
**Objetivo:** Reduzir custo do App Service (~R$42/mês → ~R$0)

## Dados básicos

| Campo | Valor |
|---|---|
| **Nome** | `az-pg-spend-analysis-ai-agent` |
| **Resource Group** | `azpgspendanalysisaiagent` |
| **Região** | Brazil South |
| **Runtime** | Python 3.13, Linux |
| **Plano atual** | Flex Consumption (FC1) |
| **Plano novo** | **Consumption (Y1)** |

## Application Settings

| Variável | Valor |
|---|---|
| `GROK_API_KEY` | `xai-...L1DV` (copiar valor completo do Portal) |
| `MODELS_DIR_PATH` | `/mount/models` |
| `DIRECT_LINE_SECRET` | `5BvM...2d5b` (copiar valor completo do Portal) |
| `POWER_AUTOMATE_URL` | `https://73e548db8cade09eb6aaf81398c987.02.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/7b5ed6ba25ec4094a1f6b7fff542f792/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=MT2lLBDmdAIKShmeVrYvC06UO0SAbAzPGn1zpWXO4tY` |
| `POWER_AUTOMATE_API_KEY` | `oLpi...lYUA` (copiar valor completo do Portal) |
| `USE_ML_CLASSIFIER` | `true` |
| `AzureWebJobsStorage` | Preenchido automaticamente se selecionar o mesmo Storage Account |

## CORS

- Origem: `https://salmon-beach-05662180f.6.azurestaticapps.net`
- Support credentials: **true**

## File Share Mount

| Campo | Valor |
|---|---|
| **Nome** | `models` |
| **Storage Account** | `azpgspendanalysisaiagent` |
| **Share name** | `models-data` |
| **Mount path** | `/mount/models` |
| **Protocolo** | SMB |

## Passos

1. **Portal Azure** → Function App → Configuration → anotar valores completos de TODAS as secrets
2. **Deletar** o Function App `az-pg-spend-analysis-ai-agent`
   - ⚠️ NÃO deletar o Resource Group nem o Storage Account
3. **Criar novo** Function App:
   - Nome: `az-pg-spend-analysis-ai-agent` (mesmo nome = mesma URL)
   - Plano: **Consumption (Y1)**
   - Runtime: **Python 3.13**
   - OS: **Linux**
   - Região: **Brazil South**
   - Storage Account: **usar existente** → `azpgspendanalysisaiagent`
4. **Application Settings** → adicionar todas as variáveis da tabela acima
5. **Configuration → Path mappings** → montar File Share:
   - Name: `models`
   - Share: `models-data`
   - Mount path: `/mount/models`
6. **CORS** → adicionar a origem do frontend com credentials
7. **Deploy**:
   ```bash
   func azure functionapp publish az-pg-spend-analysis-ai-agent --python
   ```
8. **Testar** → submeter classificação e verificar log stream

## Notas

- O File Share (`models-data`) com KBs, projetos e jobs **não é afetado** — pertence ao Storage Account
- O frontend (`salmon-beach-05662180f.6.azurestaticapps.net`) não precisa de alteração — a URL do backend permanece a mesma
- Downtime estimado: ~10 minutos
