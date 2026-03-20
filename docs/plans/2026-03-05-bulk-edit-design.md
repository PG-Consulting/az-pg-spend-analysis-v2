# Design — Edição em Massa na Tela de Revisão

**Data:** 2026-03-05
**Status:** Aprovado

## Problema

Na tela de revisão, a edição de classificação (N1-N4) só funciona item a item. Consultores precisam aplicar a mesma classificação para múltiplos itens de uma vez.

## Solução

Quando 2+ itens estão selecionados, o painel lateral (`ItemDetailPanel`) muda automaticamente para **modo bulk**: exibe cascata N1-N4 e botão "Aplicar para X itens". Sem modal, sem botão extra — comportamento implícito pela seleção.

## Fluxo do Usuário

1. Seleciona 1 item → painel lateral mostra detalhes normais (como hoje)
2. Seleciona 2+ itens → painel lateral muda para modo bulk:
   - Header: "X itens selecionados"
   - Lista resumida das descrições (scroll, max 5 visíveis)
   - Cascata N1→N2→N3→N4 (selects com `useHierarchy`, ou inputs se sem hierarquia)
   - Checkbox "Contribuir para Base de Conhecimento" (default: `globalContributeToKB`)
   - Botão "Aplicar para X itens"
3. Ao confirmar → cada item recebe `decision: 'edited'` com mesmo N1-N4
4. Seleção limpa automaticamente

## Componentes Afetados

| Componente | Mudança |
|---|---|
| `ItemDetailPanel.tsx` | Detectar `selectedCount > 1`, renderizar modo bulk (cascata + botão aplicar) |
| `useReview.ts` | Adicionar método `bulkEdit(indices, edits)` |
| `ReviewTab.tsx` | Passar `selectedIndices` ao painel lateral |
| `BulkActionBar.tsx` | Nenhuma mudança |

## Hook: `bulkEdit`

```typescript
const bulkEdit = useCallback((indices: number[], edits: {N1, N2, N3, N4, contributeToKB}) => {
  setReviewStates(prev => {
    const next = new Map(prev);
    for (const idx of indices) {
      next.set(idx, {
        decision: 'edited',
        editedN1: edits.N1,
        editedN2: edits.N2,
        editedN3: edits.N3,
        editedN4: edits.N4,
        contributeToKB: edits.contributeToKB,
      });
    }
    return next;
  });
  setSelectedIndices(new Set());
}, []);
```

## Backend

Zero alterações. O `ApproveClassifications` já recebe `decisions[]` com `decision: 'edited'` e N1-N4 por item. O bulk edit gera múltiplos itens com o mesmo N1-N4 — o backend não diferencia edição individual de edição em massa.

## Estilo

Segue design system existente. Mesmo painel lateral, mesmos selects, mesmas cores. Modo bulk é visualmente distinto apenas pelo header "X itens selecionados" e pela lista resumida de descrições.
