# Design: Download AS-IS, Toggle KB e Melhoria Import KB

Data: 2026-02-27

## Contexto

Duas solicitacoes do usuario:
1. Na tela de revisao, permitir download do Excel bruto (resultado do worker) antes de aprovar, e controle global de contribuicao para KB
2. Melhorar a experiencia de upload de conhecimento na aba KB

## Feature 1A: Download AS-IS (Excel puro do worker)

### Backend

Novo endpoint `GET /DownloadJobExcel?jobId=xxx` em `blueprints/classification_bp.py`:
- Le os `result_X.json` do job (mesma logica de `GetJobResults`)
- Gera Excel com colunas: Descricao, N1, N2, N3, N4, Fonte, Confianca
- Retorna `{filename, file_content_base64}`
- Funciona apenas se status = CLASSIFIED ou posterior
- Nome do arquivo: `{original}_resultado.xlsx`

### Frontend

- Novo metodo `apiClient.downloadJobExcel(jobId)` em `frontend/src/lib/api.ts`
- Botao "Baixar Excel" (icone download) na toolbar do `ReviewTab.tsx`, visivel sempre
- Ao clicar, chama endpoint e faz download via blob

## Feature 1B: Toggle global "Contribuir para KB"

### Hook useReview.ts

- Novo estado: `globalContributeToKB` (default `true`)
- `approveItem()` usa `globalContributeToKB` ao inves de `true` hardcoded
- `bulkApprove()` usa `globalContributeToKB` ao inves de `true` hardcoded
- `bulkApproveHighConfidence()` herda via `bulkApprove()`
- `editItem()` herda `globalContributeToKB` como default (override individual ainda funciona)
- Expoe `globalContributeToKB` e `setGlobalContributeToKB`

### Frontend — ReviewTab.tsx

Switch compacto na barra de progresso:
```
[=====progress bar=====] 85/100 85%  |  [toggle] Contribuir para KB
```
- Ligado (default): visual verde/accent
- Desligado: visual neutro/cinza
- Afeta apenas novas aprovacoes (itens ja aprovados mantem estado individual)
- Checkbox individual no ItemDetailPanel continua para override por item

### Backend

Sem mudancas — ja recebe `contribute_to_kb` por item.

## Feature 2: Melhoria UX Import KB

### O que ja existe

- `POST /ImportKB` aceita Excel base64, parseia Descricao/N1-N4, dedup por description_norm
- Botao import na KnowledgeTab (icone upload) com alert() no final

### Melhorias

1. **Preview antes de confirmar**: apos selecionar arquivo, mostrar modal/inline com:
   - Total de linhas detectadas
   - Colunas encontradas (com validacao)
   - Preview das primeiras 5 linhas
   - Botao "Confirmar Importacao"

2. **Validacao de colunas**: se faltar Descricao ou N1-N4, mostrar erro claro ANTES de enviar ao backend

3. **Feedback melhor**: substituir alert() por notificacao inline com contagem:
   - X entradas adicionadas
   - Y entradas atualizadas (se backend retornar)
   - Z total na base

### Implementacao

O parse do preview sera feito no frontend usando a lib `xlsx` (ja presente em `node_modules/xlsx`).
O envio para o backend continua via `ImportKB` existente — sem mudancas no backend.

## Arquivos Afetados

### Backend
- `blueprints/classification_bp.py` — novo endpoint DownloadJobExcel

### Frontend
- `frontend/src/lib/api.ts` — novo metodo downloadJobExcel
- `frontend/src/hooks/useReview.ts` — estado globalContributeToKB
- `frontend/src/components/taxonomy/ReviewTab.tsx` — botao download + toggle KB
- `frontend/src/components/taxonomy/KnowledgeTab.tsx` — preview de import + feedback inline

### Testes
- `tests/test_review_bp.py` ou novo `tests/test_classification_bp_download.py` — teste do endpoint DownloadJobExcel
- `frontend/__tests__/useReview.test.ts` — testes do toggle global
