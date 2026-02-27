/**
 * @fileoverview Tests for the useReview hook (Spend Analysis v3).
 *
 * The hook manages a review state machine where a consultant approves,
 * edits, or rejects each classified item before final delivery.
 *
 * We test the hook via @testing-library/react renderHook, mocking
 * IndexedDB persistence (saveReviewProgress / loadReviewProgress).
 */

import { renderHook, act } from '@testing-library/react';
import { useReview } from '../hooks/useReview';
import type { ClassifiedItem } from '../lib/types';

// ---------------------------------------------------------------------------
// Mock IndexedDB persistence layer
// ---------------------------------------------------------------------------
jest.mock('../lib/database', () => ({
  saveReviewProgress: jest.fn().mockResolvedValue(undefined),
  loadReviewProgress: jest.fn().mockResolvedValue(null),
}));

// ---------------------------------------------------------------------------
// Test data factory
// ---------------------------------------------------------------------------
function createMockItems(count: number): ClassifiedItem[] {
  const items: ClassifiedItem[] = [];
  for (let i = 0; i < count; i++) {
    items.push({
      index: i,
      description: `Item ${i} description`,
      N1: 'MRO',
      N2: 'Fixacao',
      N3: 'Parafusos',
      N4: `Parafuso Tipo ${i}`,
      confidence: 0.5 + (i % 5) * 0.1, // 0.5, 0.6, 0.7, 0.8, 0.9, 0.5, ...
      source: 'LLM',
      status: i % 3 === 0 ? 'Nenhum' : i % 3 === 1 ? 'Ambíguo' : 'Único',
    });
  }
  return items;
}

const baseMockItems: ClassifiedItem[] = [
  { index: 0, description: 'Parafuso M8', N1: 'MRO', N2: 'Fixacao', N3: 'Parafusos', N4: 'Parafuso Sextavado', confidence: 0.9, source: 'LLM', status: 'Único' },
  { index: 1, description: 'Oleo motor', N1: 'MRO', N2: 'Lubrificacao', N3: 'Oleos', N4: 'Oleo Motor', confidence: 0.3, source: 'LLM', status: 'Ambíguo' },
  { index: 2, description: 'Chave de fenda', N1: 'MRO', N2: 'Ferramentas', N3: 'Manuais', N4: 'Chave Fenda', confidence: 0.85, source: 'LLM', status: 'Único' },
  { index: 3, description: 'Peca desconhecida', N1: 'Não Identificado', N2: 'Não Identificado', N3: 'Não Identificado', N4: 'Não Identificado', confidence: 0.1, source: 'LLM', status: 'Nenhum' },
  { index: 4, description: 'Tinta azul', N1: 'MRO', N2: 'Pintura', N3: 'Tintas', N4: 'Tinta Azul', confidence: 0.75, source: 'LLM', status: 'Único' },
  { index: 5, description: 'Eletrodo', N1: 'MRO', N2: 'Soldagem', N3: 'Consumiveis', N4: 'Eletrodo Revestido', confidence: 0.4, source: 'LLM', status: 'Ambíguo' },
  { index: 6, description: 'Graxa industrial', N1: 'MRO', N2: 'Lubrificacao', N3: 'Graxas', N4: 'Graxa Industrial', confidence: 0.65, source: 'LLM', status: 'Único' },
  { index: 7, description: 'Correia dentada', N1: 'MRO', N2: 'Transmissao', N3: 'Correias', N4: 'Correia Dentada', confidence: 0.55, source: 'LLM', status: 'Único' },
  { index: 8, description: 'Rolamento 6205', N1: 'MRO', N2: 'Rolamentos', N3: 'Rolamentos Rigidos', N4: 'Rolamento 6205', confidence: 0.92, source: 'LLM', status: 'Único' },
  { index: 9, description: 'Filtro de ar', N1: 'MRO', N2: 'Filtragem', N3: 'Filtros', N4: 'Filtro Ar', confidence: 0.88, source: 'LLM', status: 'Único' },
];

// ---------------------------------------------------------------------------
// Helper to render the hook
// ---------------------------------------------------------------------------
function renderUseReview(items: ClassifiedItem[] = baseMockItems) {
  return renderHook(() =>
    useReview({
      sessionId: 'test-session-001',
      items,
    })
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useReview', () => {
  // 1. Initial state
  it('should start with all items as pending', async () => {
    const { result } = renderUseReview();

    // Wait for isLoading to become false (loadReviewProgress resolves)
    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.progress.total).toBe(10);
    expect(result.current.progress.pending).toBe(10);
    expect(result.current.progress.approved).toBe(0);
    expect(result.current.progress.edited).toBe(0);
    expect(result.current.progress.rejected).toBe(0);
  });

  // 2. Approve item
  it('should change item state to approved when approveItem is called', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.approveItem(0);
    });

    const state = result.current.getItemState(0);
    expect(state.decision).toBe('approved');
    expect(state.contributeToKB).toBe(true);
    expect(result.current.progress.approved).toBe(1);
    expect(result.current.progress.pending).toBe(9);
  });

  // 3. Edit item
  it('should change item state to edited with new N1-N4 values', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.editItem(1, {
        N1: 'MRO',
        N2: 'Lubrificacao',
        N3: 'Oleos',
        N4: 'Oleo Sintetico',
        contributeToKB: true,
      });
    });

    const state = result.current.getItemState(1);
    expect(state.decision).toBe('edited');
    expect(state.editedN1).toBe('MRO');
    expect(state.editedN2).toBe('Lubrificacao');
    expect(state.editedN3).toBe('Oleos');
    expect(state.editedN4).toBe('Oleo Sintetico');
    expect(state.contributeToKB).toBe(true);
    expect(result.current.progress.edited).toBe(1);
  });

  // 4. Reject item
  it('should change item state to rejected with optional instruction', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.rejectItem(3, 'Reclassificar como material de consumo');
    });

    const state = result.current.getItemState(3);
    expect(state.decision).toBe('rejected');
    expect(state.instructionUsed).toBe('Reclassificar como material de consumo');
    expect(result.current.progress.rejected).toBe(1);
  });

  // 5. Progress calculation
  it('should calculate correct progress with mixed review states', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    // Approve 3 items
    act(() => {
      result.current.approveItem(0);
      result.current.approveItem(2);
      result.current.approveItem(8);
    });

    // Edit 2 items
    act(() => {
      result.current.editItem(1, { N1: 'MRO', N2: 'Lub', N3: 'Oleos', N4: 'Oleo X' });
      result.current.editItem(6, { N1: 'MRO', N2: 'Lub', N3: 'Graxas', N4: 'Graxa Y' });
    });

    expect(result.current.progress.total).toBe(10);
    expect(result.current.progress.approved).toBe(3);
    expect(result.current.progress.edited).toBe(2);
    expect(result.current.progress.rejected).toBe(0);
    expect(result.current.progress.reviewed).toBe(5);
    expect(result.current.progress.pending).toBe(5);
    expect(result.current.progress.pct).toBe(50);
  });

  // 6. Filter pending
  it('should filter to only pending items when filter is set to pending', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    // Approve some items first
    act(() => {
      result.current.approveItem(0);
      result.current.approveItem(2);
      result.current.approveItem(4);
    });

    act(() => {
      result.current.setFilter('pending');
    });

    // filteredItems should only have items that are still pending
    const filteredIndices = result.current.filteredItems.map(i => i.index);
    expect(filteredIndices).not.toContain(0);
    expect(filteredIndices).not.toContain(2);
    expect(filteredIndices).not.toContain(4);
    expect(result.current.filteredItems).toHaveLength(7);
  });

  // 7. Filter low_confidence
  it('should filter to items with confidence < 0.7 when filter is low_confidence', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.setFilter('low_confidence');
    });

    // Items with confidence < 0.7: indices 1 (0.3), 3 (0.1), 5 (0.4), 6 (0.65), 7 (0.55)
    const filtered = result.current.filteredItems;
    filtered.forEach(item => {
      expect(item.confidence).toBeLessThan(0.7);
    });
    expect(filtered.length).toBe(5);
  });

  // 8. Filter approved
  it('should filter to only approved items when filter is set to approved', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.approveItem(0);
      result.current.approveItem(8);
      result.current.approveItem(9);
    });

    act(() => {
      result.current.setFilter('approved');
    });

    expect(result.current.filteredItems).toHaveLength(3);
    result.current.filteredItems.forEach(item => {
      expect(result.current.getItemState(item.index).decision).toBe('approved');
    });
  });

  // 9. Filter corrected (edited items)
  it('should filter to only edited items when filter is set to corrected', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.editItem(1, { N1: 'X', N2: 'Y', N3: 'Z', N4: 'W' });
      result.current.editItem(5, { N1: 'A', N2: 'B', N3: 'C', N4: 'D' });
      result.current.approveItem(0);
    });

    act(() => {
      result.current.setFilter('corrected');
    });

    expect(result.current.filteredItems).toHaveLength(2);
    const indices = result.current.filteredItems.map(i => i.index);
    expect(indices).toContain(1);
    expect(indices).toContain(5);
  });

  // 10. Bulk approve
  it('should mark multiple items as approved via bulkApprove', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.bulkApprove([0, 2, 4, 8, 9]);
    });

    expect(result.current.progress.approved).toBe(5);
    expect(result.current.progress.pending).toBe(5);
    expect(result.current.getItemState(0).decision).toBe('approved');
    expect(result.current.getItemState(2).decision).toBe('approved');
    expect(result.current.getItemState(4).decision).toBe('approved');
    expect(result.current.getItemState(8).decision).toBe('approved');
    expect(result.current.getItemState(9).decision).toBe('approved');
    // Unapproved items remain pending
    expect(result.current.getItemState(1).decision).toBe('pending');
  });

  // 11. canFinalize when all items reviewed
  it('should set canFinalize to true when all items have been reviewed', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    expect(result.current.canFinalize).toBe(false);

    // Review all 10 items
    act(() => {
      result.current.bulkApprove([0, 2, 4, 6, 8, 9]);
      result.current.editItem(1, { N1: 'A', N2: 'B', N3: 'C', N4: 'D' });
      result.current.editItem(5, { N1: 'E', N2: 'F', N3: 'G', N4: 'H' });
      result.current.rejectItem(3);
      result.current.rejectItem(7);
    });

    expect(result.current.canFinalize).toBe(true);
    expect(result.current.progress.pending).toBe(0);
  });

  // 12. canFinalize is false with pending items
  it('should set canFinalize to false when items are still pending', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    act(() => {
      result.current.approveItem(0);
      result.current.approveItem(1);
    });

    // 8 items still pending
    expect(result.current.canFinalize).toBe(false);
    expect(result.current.progress.pending).toBe(8);
  });

  // 13. Toggle selection
  it('should add and remove indices from selectedIndices via toggleSelection', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    // Select item 3
    act(() => {
      result.current.toggleSelection(3);
    });
    expect(result.current.selectedIndices.has(3)).toBe(true);
    expect(result.current.selectedIndices.size).toBe(1);

    // Select item 7
    act(() => {
      result.current.toggleSelection(7);
    });
    expect(result.current.selectedIndices.has(3)).toBe(true);
    expect(result.current.selectedIndices.has(7)).toBe(true);
    expect(result.current.selectedIndices.size).toBe(2);

    // Deselect item 3
    act(() => {
      result.current.toggleSelection(3);
    });
    expect(result.current.selectedIndices.has(3)).toBe(false);
    expect(result.current.selectedIndices.has(7)).toBe(true);
    expect(result.current.selectedIndices.size).toBe(1);
  });

  // 14. Toggle all
  it('should select all filtered items on toggleAll, then deselect on second call', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    // Set filter to 'all' to ensure we see all items
    act(() => {
      result.current.setFilter('all');
    });

    // Toggle all ON
    act(() => {
      result.current.toggleAll();
    });

    expect(result.current.selectedIndices.size).toBe(result.current.filteredItems.length);

    // Toggle all OFF
    act(() => {
      result.current.toggleAll();
    });

    expect(result.current.selectedIndices.size).toBe(0);
  });

  // 15. Sort pending first
  it('should sort pending items before approved items in filteredItems', async () => {
    const { result } = renderUseReview();

    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });

    // Set filter to 'all' so we see everything
    act(() => {
      result.current.setFilter('all');
    });

    // Approve items 0, 2, 4
    act(() => {
      result.current.approveItem(0);
      result.current.approveItem(2);
      result.current.approveItem(4);
    });

    const filtered = result.current.filteredItems;

    // Find the position of the first approved item in the sorted list
    const firstApprovedIdx = filtered.findIndex(
      item => result.current.getItemState(item.index).decision === 'approved'
    );

    // All items before firstApprovedIdx should be pending
    for (let i = 0; i < firstApprovedIdx; i++) {
      expect(result.current.getItemState(filtered[i].index).decision).toBe('pending');
    }

    // From firstApprovedIdx onward, all should be approved (or at least non-pending)
    for (let i = firstApprovedIdx; i < filtered.length; i++) {
      expect(result.current.getItemState(filtered[i].index).decision).not.toBe('pending');
    }

    // Verify pending count is 7 (10 total minus 3 approved)
    const pendingInList = filtered.filter(
      item => result.current.getItemState(item.index).decision === 'pending'
    );
    expect(pendingInList).toHaveLength(7);
  });

  // 16. Global contributeToKB toggle
  it('should default globalContributeToKB to true', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    expect(result.current.globalContributeToKB).toBe(true);
  });

  // 17. approveItem uses globalContributeToKB
  it('should use globalContributeToKB=false when approving items', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });

    act(() => { result.current.setGlobalContributeToKB(false); });
    act(() => { result.current.approveItem(0); });

    expect(result.current.getItemState(0).contributeToKB).toBe(false);
  });

  // 18. bulkApprove uses globalContributeToKB
  it('should use globalContributeToKB=false in bulk approve', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });

    act(() => { result.current.setGlobalContributeToKB(false); });
    act(() => { result.current.bulkApprove([0, 1, 2]); });

    expect(result.current.getItemState(0).contributeToKB).toBe(false);
    expect(result.current.getItemState(1).contributeToKB).toBe(false);
    expect(result.current.getItemState(2).contributeToKB).toBe(false);
  });

  // 19. editItem uses globalContributeToKB as default
  it('should use globalContributeToKB as default for editItem', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });

    act(() => { result.current.setGlobalContributeToKB(false); });
    act(() => {
      result.current.editItem(1, { N1: 'A', N2: 'B', N3: 'C', N4: 'D' });
    });

    expect(result.current.getItemState(1).contributeToKB).toBe(false);
  });

  // 20. editItem explicit override still works
  it('should allow explicit contributeToKB override in editItem', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });

    act(() => { result.current.setGlobalContributeToKB(false); });
    act(() => {
      result.current.editItem(1, { N1: 'A', N2: 'B', N3: 'C', N4: 'D', contributeToKB: true });
    });

    expect(result.current.getItemState(1).contributeToKB).toBe(true);
  });
});
