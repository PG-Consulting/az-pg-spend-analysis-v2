# Design: Download Excel com Progresso de Revisão

**Data:** 2026-03-11
**Status:** Reviewed (CRITICALs corrigidos)
**Motivação:** Consultores fazem correções na tela de revisão mas, ao baixar o Excel, perdem todas as alterações. Para obter o Excel com correções, precisam finalizar a revisão inteira — inviável para arquivos grandes onde parte do trabalho é feita na planilha.

## Problema

1. `DownloadJobExcel` (GET) retorna resultado bruto do pipeline — sem correções da revisão
2. `ApproveClassifications` (POST) gera Excel com correções — mas exige finalização (status → COMPLETED)
3. Não existe meio-termo: baixar Excel com alterações parciais sem finalizar

## Solução

Estender `DownloadJobExcel` para aceitar POST com decisions parciais do frontend. O backend mescla decisions com `result.json` e gera Excel refletindo correções + coluna "Status".

## Arquitetura

### Backend — `DownloadJobExcel` (classification_bp.py)

**Mudança:** aceitar POST além de GET. Atualizar `options_response` para incluir POST nos métodos permitidos (CORS).

- **GET** (sem body): comportamento atual inalterado — Excel bruto do pipeline
- **POST** com `{ "decisions": [...] }`: mescla decisions com result.json

**CORS:** A chamada `options_response(req, "GET, OPTIONS")` deve ser atualizada para `options_response(req, "GET, POST, OPTIONS")`. Sem isso, o browser bloqueia o POST via CORS preflight.

**Route:** `methods=["GET", "POST", "OPTIONS"]`.

Formato de cada decision:
```json
{
  "index": 0,
  "decision": "approved|edited|rejected",
  "N1": "Categoria", "N2": "Sub", "N3": "Grupo", "N4": "Item"
}
```

**Validação do payload:**
- `decision` deve ser um de `("approved", "edited", "rejected")` — rejeitar valores inválidos
- `index` deve ser inteiro `>= 0` e `< len(raw_items)` — rejeitar se fora do range
- `len(decisions) <= len(raw_items)` — rejeitar se mais decisions que itens
- Índices duplicados: usar o último encontrado (silenciosamente — frontend não deveria enviar duplicatas, mas se enviar, o último ganha)

Regras de merge por item:
| Tem decision? | decision     | N1-N4 no Excel          | Fonte no Excel        | Status     |
|---------------|-------------|-------------------------|-----------------------|------------|
| Não           | —           | Pipeline (result.json)  | Pipeline (direto*)    | Pendente   |
| Sim           | `approved`  | Pipeline (result.json)  | Pipeline (direto*)    | Aprovado   |
| Sim           | `edited`    | Da decision (corrigido) | "Ajuste Manual"       | Editado    |
| Sim           | `rejected`  | Pipeline (result.json)  | Pipeline (direto*)    | Rejeitado  |

> \* **Nota sobre Fonte:** `result.json` já armazena labels amigáveis ("Grok", "Base de Aprendizado") — o worker aplica `friendly_source_label()` durante consolidação. No path POST, a coluna Fonte deve usar `item.get("source", "")` **diretamente**, sem chamar `friendly_source_label()` novamente. Para itens editados, setar `"Ajuste Manual"` diretamente. O path GET existente já chama `friendly_source_label()` e funciona por acidente (labels desconhecidas retornam elas mesmas como fallback) — manter inalterado para não quebrar backward compat.

Coluna "Status" adicionada como **última coluna** do Excel. A coluna Status é adicionada sempre que o request for POST (mesmo com decisions vazio — todos ficam "Pendente"). No GET, a coluna NÃO é adicionada (backward compat).

Apenas itens com `decision != "pending"` são enviados no payload (ausência = pendente). Isso minimiza o tamanho do request.

O status do job **não é alterado** — permanece CLASSIFIED.

Sheet name: `"Resultados"` (igual ao GET).
Filename: `{original}_resultado.xlsx` (igual ao GET).

**Diferença vs Excel de finalização:** O Excel deste endpoint inclui TODOS os itens (inclusive rejeitados, com Status="Rejeitado"). O Excel de `ApproveClassifications` exclui rejeitados. Isso é intencional — aqui é working copy, lá é resultado final.

### Frontend — ReviewTab + api.ts

**`api.ts`:** método `downloadJobExcel` ganha parâmetro opcional `decisions`:
- Se `decisions` presente → POST com body `{ decisions }`
- Se ausente → GET (retrocompatível)

**`ReviewTab.tsx`:** `handleDownloadAsIs` passa a:
1. Iterar `localItems`, chamar `getItemState(item.index)` para cada
2. Filtrar apenas itens com `decision != "pending"`
3. Montar array de decisions com `{ index, decision, N1, N2, N3, N4 }`
4. Chamar `apiClient.downloadJobExcel(jobId, decisions)`

Para itens editados, N1-N4 vêm do `state.editedN1/N2/N3/N4`.
Para aprovados/rejeitados, N1-N4 vêm do `item.N1/N2/N3/N4` original.

### O que NÃO muda

- Fluxo de finalização (`ApproveClassifications`) — inalterado
- Status do job — download não altera estado
- Excel da finalização — sem coluna Status (é resultado final, não working copy)
- KB — não alimentada nesse download (só na finalização)
- GET sem body — retrocompatível

## Coluna Status — Valores

| Valor      | Significado                                    |
|------------|------------------------------------------------|
| Pendente   | Item não revisado pelo consultor               |
| Aprovado   | Classificação do pipeline aceita               |
| Editado    | Classificação corrigida manualmente            |
| Rejeitado  | Item marcado para exclusão                     |

## Estimativa de Payload

Para 10.000 itens onde 3.000 foram revisados:
- ~3.000 decisions enviadas (pendentes omitidos)
- ~150 bytes/decision × 3.000 = ~450KB
- Dentro do limite razoável para POST

## Arquivos Impactados

| Arquivo | Mudança |
|---------|---------|
| `blueprints/classification_bp.py` | Aceitar POST, parse decisions, merge com result.json, coluna Status |
| `frontend/src/lib/api.ts` | `downloadJobExcel` com parâmetro opcional decisions, POST condicional |
| `frontend/src/components/taxonomy/ReviewTab.tsx` | `handleDownloadAsIs` coleta e envia decisions |
| `tests/test_download_job_excel.py` | Novos testes: POST com decisions, merge, coluna Status |
| `frontend/__tests__/` | Teste do api.ts com decisions |

## Testes

### Backend
1. GET sem body → comportamento atual (sem coluna Status)
2. POST com decisions vazio → inclui coluna Status com todos "Pendente"
3. POST com mix de approved/edited/rejected/pendente → verifica N1-N4, Fonte, Status de cada
4. POST com item editado → N1-N4 da decision, Fonte = "Ajuste Manual", Status = "Editado"
5. POST com item rejeitado → inclui no Excel com Status = "Rejeitado" (não exclui)

### Frontend
6. `downloadJobExcel` com decisions → faz POST
7. `downloadJobExcel` sem decisions → faz GET
8. `handleDownloadAsIs` monta decisions corretamente a partir de reviewStates
