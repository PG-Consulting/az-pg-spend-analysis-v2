# Design: Fixes do Feedback do Cliente (2026-03-09)

## Contexto

Feedback recebido do cliente com 5 pontos. Após triagem, 3 são acionáveis agora:

| # | Problema | Tipo |
|---|----------|------|
| 1 | Fornecedor não aparece na tela de revisão | Bug frontend |
| 2 | Chat do agente não limpa | Bug frontend |
| 3 | Fixes anteriores não refletiram na ferramenta | Deploy pendente |

Pontos descartados nesta iteração:
- **Coluna Excel "Fonte"**: já implementada corretamente, problema é deploy
- **Flag não limpo**: ambíguo, aguardando clarificação do cliente

## Fix 1 — Fornecedor na ReviewTable

### Situação atual
- Backend extrai `extra_columns` do Excel de upload (qualquer coluna além de ID e Descrição que não seja reservada)
- Backend inclui `extra_columns` no `status.json` do job e nos dados de cada item
- Excel de saída já inclui colunas extras
- **Frontend NÃO renderiza** essas colunas na tabela de revisão

### Solução
- Ler `extra_columns` da resposta do job no frontend
- Renderizar uma coluna por cada extra column na ReviewTable, posicionada entre "Descrição" e "Classificação"
- Dados já disponíveis em cada item (ex: `item.Fornecedor`)
- Abordagem: colunas fixas visíveis (decisão do usuário)

### Arquivos afetados
- `frontend/src/components/taxonomy/ReviewTable.tsx` — adicionar colunas dinâmicas
- `frontend/src/lib/types.ts` — verificar se tipo suporta `extra_columns`
- `frontend/src/hooks/useReview.ts` — verificar se `extra_columns` é propagado

## Fix 2 — resetChat() não limpa mensagens

### Situação atual
- `resetChat()` em `useCopilot.ts` só reseta `isCopilotLoading`, `isSending` e `userMessage`
- `copilotMessages` e `chatHistory` NÃO são limpos
- Chat persiste via `localStorage` com chave `pg_spend_chat_{sessionId}`
- `resetChat()` não é chamado ao finalizar revisão

### Solução
- Modificar `resetChat()` para limpar `copilotMessages`, `chatHistory` e `localStorage`
- Garantir que `resetChat()` é chamado ao finalizar revisão e ao trocar de job

### Arquivos afetados
- `frontend/src/hooks/useCopilot.ts` — expandir `resetChat()`
- `frontend/src/pages/taxonomy.tsx` — chamar `resetChat()` nos pontos corretos

## Fix 3 — Deploy pendente

### Ação
- Verificar último deploy do backend
- Executar `func azure functionapp publish az-pg-spend-analysis-ai-agent --python`
- Validar que fixes de "Não Identificado" e coluna "Fonte" estão ativos
