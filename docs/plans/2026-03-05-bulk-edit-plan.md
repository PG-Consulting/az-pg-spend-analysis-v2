# Edição em Massa — Plano de Implementação

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Permitir que consultores selecionem 2+ itens na tela de revisão e apliquem a mesma classificação N1-N4 para todos de uma vez, via modo bulk automático no painel lateral.

**Architecture:** O painel lateral (`ItemDetailPanel`) detecta quando `selectedIndices.size > 1` e renderiza um modo bulk com cascata N1-N4 e botão "Aplicar". Um novo método `bulkEdit` no hook `useReview` marca todos os índices selecionados como `edited` com os mesmos valores. Zero alterações no backend.

**Tech Stack:** React 18, TypeScript, TailwindCSS, Jest + @testing-library/react

---

### Task 1: Adicionar `bulkEdit` ao hook `useReview`

**Files:**
- Modify: `frontend/src/hooks/useReview.ts:167-178` (inserir antes de `bulkApprove`)
- Test: `frontend/src/__tests__/useReview.test.ts`

**Step 1: Escrever o teste**

Adicionar ao final do arquivo de teste, antes do `});` que fecha o `describe`:

```typescript
  // bulkEdit — edição em massa
  it('should mark multiple items as edited with same N1-N4 via bulkEdit', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.bulkEdit([1, 3, 5], {
        N1: 'Servicos',
        N2: 'Manutencao',
        N3: 'Preventiva',
        N4: 'Inspecao Geral',
        contributeToKB: true,
      });
    });

    // All 3 items should be edited with same classification
    for (const idx of [1, 3, 5]) {
      const state = result.current.getItemState(idx);
      expect(state.decision).toBe('edited');
      expect(state.editedN1).toBe('Servicos');
      expect(state.editedN2).toBe('Manutencao');
      expect(state.editedN3).toBe('Preventiva');
      expect(state.editedN4).toBe('Inspecao Geral');
      expect(state.contributeToKB).toBe(true);
    }

    // Other items remain pending
    expect(result.current.getItemState(0).decision).toBe('pending');
    expect(result.current.getItemState(2).decision).toBe('pending');

    // Progress reflects edits
    expect(result.current.progress.edited).toBe(3);
    expect(result.current.progress.pending).toBe(7);

    // Selection should be cleared
    expect(result.current.selectedIndices.size).toBe(0);
  });

  it('should count bulkEdit items in corrected filter', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.bulkEdit([0, 4, 8], {
        N1: 'A', N2: 'B', N3: 'C', N4: 'D',
        contributeToKB: false,
      });
    });

    act(() => {
      result.current.setFilter('corrected');
    });

    expect(result.current.filteredItems).toHaveLength(3);
    expect(result.current.filterCounts.corrected).toBe(3);
  });
```

**Step 2: Rodar teste para verificar que falha**

Run: `cd frontend && npx jest --verbose --testPathPattern useReview -t "bulkEdit"`
Expected: FAIL — `result.current.bulkEdit is not a function`

**Step 3: Implementar `bulkEdit` no hook**

Em `frontend/src/hooks/useReview.ts`, adicionar após `reclassifyItems` (linha 166) e antes de `bulkApprove` (linha 168):

```typescript
  const bulkEdit = useCallback((indices: number[], edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB: boolean }) => {
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

Adicionar `bulkEdit` ao objeto retornado (após `reclassifyItems` na linha 248):

```typescript
    bulkEdit,
```

**Step 4: Rodar teste para verificar que passa**

Run: `cd frontend && npx jest --verbose --testPathPattern useReview -t "bulkEdit"`
Expected: PASS (2 testes)

**Step 5: Rodar toda a suíte para garantir que nada quebrou**

Run: `cd frontend && npx jest --verbose`
Expected: todos os 48+ testes passando

**Step 6: Commit**

```bash
git add frontend/src/hooks/useReview.ts frontend/src/__tests__/useReview.test.ts
git commit -m "Adicionando bulkEdit ao hook useReview (edição em massa)"
```

---

### Task 2: Adicionar modo bulk ao `ItemDetailPanel`

**Files:**
- Modify: `frontend/src/components/taxonomy/ItemDetailPanel.tsx`

**Step 1: Adicionar novas props ao componente**

Em `ItemDetailPanelProps` (linha 14), adicionar:

```typescript
  // Bulk edit mode
  selectedItems?: ClassifiedItem[];
  onBulkEdit?: (edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB: boolean }) => void;
```

Adicionar às props desestruturadas do componente (linha 27):

```typescript
  selectedItems,
  onBulkEdit,
```

**Step 2: Adicionar renderização do modo bulk**

Após o check de empty state (`if (!item)` no bloco que retorna na linha 120), adicionar o check de modo bulk:

```typescript
  // Bulk edit mode
  if (selectedItems && selectedItems.length > 1 && onBulkEdit) {
    return (
      <BulkEditPanel
        selectedItems={selectedItems}
        hierarchy={hierarchy}
        onBulkEdit={onBulkEdit}
      />
    );
  }
```

**Step 3: Criar o componente `BulkEditPanel` no mesmo arquivo**

Adicionar antes do `export function ItemDetailPanel`:

```typescript
function BulkEditPanel({
  selectedItems,
  hierarchy,
  onBulkEdit,
}: {
  selectedItems: ClassifiedItem[];
  hierarchy: HierarchyEntry[] | null;
  onBulkEdit: (edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB: boolean }) => void;
}) {
  const { n1Options, getN2Options, getN3Options, getN4Options, hasHierarchy } = useHierarchy(hierarchy);

  const [n1, setN1] = useState('');
  const [n2, setN2] = useState('');
  const [n3, setN3] = useState('');
  const [n4, setN4] = useState('');
  const [contributeToKB, setContributeToKB] = useState(true);

  const handleN1Change = (val: string) => { setN1(val); setN2(''); setN3(''); setN4(''); };
  const handleN2Change = (val: string) => { setN2(val); setN3(''); setN4(''); };
  const handleN3Change = (val: string) => { setN3(val); setN4(''); };

  const n2Options = getN2Options(n1);
  const n3Options = getN3Options(n1, n2);
  const n4Options = getN4Options(n1, n2, n3);

  const canApply = n1 && n2 && n3 && n4;

  const selectClass = "w-full h-10 rounded-xl border border-gray-200 bg-white pl-3 pr-8 text-sm shadow-[0_2px_8px_rgba(28,9,87,0.04)] transition-colors appearance-none focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] focus:outline-none";
  const inputClass = "w-full h-10 rounded-xl border border-gray-200 bg-white px-3 text-sm shadow-[0_2px_8px_rgba(28,9,87,0.04)] transition-colors focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] focus:outline-none";

  const renderField = (label: string, value: string, onChange: (v: string) => void, options: string[]) => (
    <div>
      <label className="block text-[11px] font-medium text-primary-400 uppercase tracking-wider mb-1.5">{label}</label>
      {hasHierarchy && options.length > 0 ? (
        <div className="relative">
          <select
            value={value}
            onChange={e => onChange(e.target.value)}
            className={selectClass}
          >
            <option value="">Selecionar...</option>
            {options.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none">
            <svg className="h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M5.22 8.22a.75.75 0 011.06 0L10 11.94l3.72-3.72a.75.75 0 111.06 1.06l-4.25 4.25a.75.75 0 01-1.06 0L5.22 9.28a.75.75 0 010-1.06z" clipRule="evenodd" />
            </svg>
          </div>
        </div>
      ) : (
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          className={inputClass}
          placeholder={`${label}...`}
        />
      )}
    </div>
  );

  return (
    <div className="w-96 border-l border-gray-100 bg-white flex flex-col overflow-y-auto">
      <div className="p-5 space-y-5">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-accent-50 flex items-center justify-center flex-shrink-0">
            <span className="text-sm font-bold text-accent-600">{selectedItems.length}</span>
          </div>
          <div>
            <p className="text-sm font-medium text-[#32373c]">{selectedItems.length} itens selecionados</p>
            <p className="text-[11px] text-primary-400">Edição em massa</p>
          </div>
        </div>

        {/* Items preview */}
        <div className="max-h-32 overflow-y-auto space-y-1 rounded-xl bg-gray-50 p-3 border border-gray-100">
          {selectedItems.slice(0, 5).map(item => (
            <p key={item.index} className="text-xs text-primary-600 truncate" title={item.description}>
              {item.description}
            </p>
          ))}
          {selectedItems.length > 5 && (
            <p className="text-xs text-primary-400 italic">
              +{selectedItems.length - 5} itens...
            </p>
          )}
        </div>

        {/* Divider */}
        <div className="border-t border-gray-100" />

        {/* N1-N4 Cascading Dropdowns */}
        <div className="space-y-3">
          <p className="text-[11px] font-medium text-primary-400 uppercase tracking-wider">Nova classificação</p>
          {renderField('N1', n1, handleN1Change, n1Options)}
          {renderField('N2', n2, handleN2Change, n2Options)}
          {renderField('N3', n3, handleN3Change, n3Options)}
          {renderField('N4', n4, setN4, n4Options)}
        </div>

        {/* Contribute to KB */}
        <label className="flex items-center gap-2.5 cursor-pointer group">
          <input
            type="checkbox"
            checked={contributeToKB}
            onChange={e => setContributeToKB(e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 text-accent-500 focus:ring-accent-500/25"
          />
          <span className="text-sm text-primary-600 group-hover:text-[#32373c] transition-colors">
            Contribuir para Base de Conhecimento
          </span>
        </label>

        {/* Divider */}
        <div className="border-t border-gray-100" />

        {/* Apply button */}
        <button
          onClick={() => onBulkEdit({ N1: n1, N2: n2, N3: n3, N4: n4, contributeToKB })}
          disabled={!canApply}
          className="w-full py-2.5 px-4 rounded-xl text-sm font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed bg-accent-500 text-white hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-accent-500/25 focus:ring-offset-1"
        >
          Aplicar para {selectedItems.length} itens
        </button>
      </div>
    </div>
  );
}
```

**Step 4: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros

**Step 5: Commit**

```bash
git add frontend/src/components/taxonomy/ItemDetailPanel.tsx
git commit -m "Adicionando modo bulk ao ItemDetailPanel (edição em massa)"
```

---

### Task 3: Conectar `ReviewTab` ao modo bulk

**Files:**
- Modify: `frontend/src/components/taxonomy/ReviewTab.tsx:42-46` (desestruturar `bulkEdit`)
- Modify: `frontend/src/components/taxonomy/ReviewTab.tsx:375-386` (passar novas props ao `ItemDetailPanel`)

**Step 1: Desestruturar `bulkEdit` do hook**

Na linha 45 de `ReviewTab.tsx`, adicionar `bulkEdit` à desestruturação:

```typescript
    approveItem, editItem, rejectItem, rejectItems, reclassifyItems, bulkApprove, bulkApproveHighConfidence,
    bulkEdit,
```

**Step 2: Criar `selectedItems` derivado e handler**

Após `activeItemState` (linha 95), adicionar:

```typescript
  const selectedItemsList = useMemo(
    () => selectedIndices.size > 1 ? localItems.filter(i => selectedIndices.has(i.index)) : [],
    [selectedIndices, localItems]
  );

  const handleBulkEdit = useCallback((edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB: boolean }) => {
    bulkEdit(Array.from(selectedIndices), edits);
  }, [bulkEdit, selectedIndices]);
```

**Step 3: Passar novas props ao `ItemDetailPanel`**

Atualizar o bloco do `ItemDetailPanel` (linha 375):

```typescript
      <ItemDetailPanel
        item={activeItem}
        itemState={activeItemState}
        hierarchy={hierarchy}
        onApprove={approveItem}
        onApproveWithEdit={(index, edits) => editItem(index, edits)}
        onReject={handleRejectSingle}
        onPrev={navigatePrev}
        onNext={navigateNext}
        hasPrev={activeDisplayIdx > 0}
        hasNext={activeDisplayIdx < displayItems.length - 1}
        selectedItems={selectedItemsList}
        onBulkEdit={handleBulkEdit}
      />
```

**Step 4: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros

**Step 5: Rodar toda a suíte de testes**

Run: `cd frontend && npx jest --verbose`
Expected: todos os testes passando

**Step 6: Commit**

```bash
git add frontend/src/components/taxonomy/ReviewTab.tsx
git commit -m "Conectando ReviewTab ao modo bulk do ItemDetailPanel"
```

---

### Task 4: Teste de integração manual e ajustes finais

**Step 1: Rodar toda a suíte de testes**

Run: `cd frontend && npx jest --verbose`
Expected: todos os testes passando (50+ testes)

**Step 2: Verificar TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros

**Step 3: Commit final se necessário**

```bash
git add -A
git commit -m "Ajustes finais — edição em massa na tela de revisão"
```
