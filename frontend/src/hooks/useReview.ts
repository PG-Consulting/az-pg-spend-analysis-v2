import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import type { ClassifiedItem, ReviewDecision, ReviewFilter, ReviewItemState } from '../lib/types';
import { saveReviewProgress, loadReviewProgress } from '../lib/database';

interface UseReviewOptions {
  sessionId: string;
  items: ClassifiedItem[];
  onComplete?: (decisions: ReviewDecision[]) => void;
}

export function useReview({ sessionId, items, onComplete }: UseReviewOptions) {
  // Map of item index → review state
  const [reviewStates, setReviewStates] = useState<Map<number, ReviewItemState>>(new Map());
  const [filter, setFilter] = useState<ReviewFilter>('all');
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const autoSaveTimer = useRef<NodeJS.Timeout>();

  // Load saved progress on mount
  useEffect(() => {
    if (!sessionId || items.length === 0) return;
    loadReviewProgress(sessionId).then(saved => {
      if (saved && saved.size > 0) {
        setReviewStates(saved);
      }
      setIsLoading(false);
    });
  }, [sessionId, items.length]);

  // Default to low_confidence filter when there are such items (better UX for large files)
  useEffect(() => {
    if (!isLoading && items.length > 0) {
      const hasLowConf = items.some(i => i.confidence < 0.7);
      if (hasLowConf) setFilter('low_confidence');
    }
  }, [isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-save every 5 seconds
  useEffect(() => {
    if (isLoading) return;
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => {
      saveReviewProgress(sessionId, reviewStates);
    }, 5000);
    return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current); };
  }, [reviewStates, sessionId, isLoading]);

  // Derived: filtered items sorted smartly
  const filteredItems = useMemo(() => {
    let result = [...items];

    // Apply filter
    if (filter !== 'all') {
      result = result.filter(item => {
        const state = reviewStates.get(item.index);
        const decision = state?.decision || 'pending';
        switch (filter) {
          case 'needs_attention': return item.confidence < 0.45 || item.status === 'Nenhum';
          case 'low_confidence': return item.confidence < 0.7;
          case 'corrected': return decision === 'edited';
          case 'approved': return decision === 'approved';
          case 'rejected': return decision === 'rejected';
          case 'pending': return decision === 'pending';
          default: return true;
        }
      });
    }

    // Sort: pending first, then by confidence ascending (lowest confidence needs most attention)
    result.sort((a, b) => {
      const stateA = reviewStates.get(a.index)?.decision || 'pending';
      const stateB = reviewStates.get(b.index)?.decision || 'pending';
      if (stateA === 'pending' && stateB !== 'pending') return -1;
      if (stateA !== 'pending' && stateB === 'pending') return 1;
      if (stateA === 'pending' && stateB === 'pending') return a.confidence - b.confidence;
      return 0;
    });

    return result;
  }, [items, filter, reviewStates]);

  // Progress
  const progress = useMemo(() => {
    const total = items.length;
    const reviewed = items.filter(item => {
      const state = reviewStates.get(item.index);
      return state && state.decision !== 'pending';
    }).length;
    const approved = items.filter(item => reviewStates.get(item.index)?.decision === 'approved').length;
    const edited = items.filter(item => reviewStates.get(item.index)?.decision === 'edited').length;
    const rejected = items.filter(item => reviewStates.get(item.index)?.decision === 'rejected').length;
    const pending = total - reviewed;

    return { total, reviewed, approved, edited, rejected, pending, pct: total > 0 ? Math.round((reviewed / total) * 100) : 0 };
  }, [items, reviewStates]);

  // Filter counts
  const filterCounts = useMemo(() => ({
    all: items.length,
    needs_attention: items.filter(i => i.confidence < 0.45 || i.status === 'Nenhum').length,
    low_confidence: items.filter(i => i.confidence < 0.7).length,
    corrected: items.filter(i => reviewStates.get(i.index)?.decision === 'edited').length,
    approved: items.filter(i => reviewStates.get(i.index)?.decision === 'approved').length,
    rejected: items.filter(i => reviewStates.get(i.index)?.decision === 'rejected').length,
    pending: items.filter(i => !reviewStates.get(i.index) || reviewStates.get(i.index)?.decision === 'pending').length,
  }), [items, reviewStates]);

  const canFinalize = progress.pending === 0;

  // Actions
  const approveItem = useCallback((index: number) => {
    setReviewStates(prev => {
      const next = new Map(prev);
      const existing = next.get(index) || { decision: 'pending' as ReviewDecision };
      next.set(index, { ...existing, decision: 'approved', contributeToKB: existing.contributeToKB ?? true });
      return next;
    });
  }, []);

  const editItem = useCallback((index: number, edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB?: boolean }) => {
    setReviewStates(prev => {
      const next = new Map(prev);
      next.set(index, {
        decision: 'edited',
        editedN1: edits.N1,
        editedN2: edits.N2,
        editedN3: edits.N3,
        editedN4: edits.N4,
        contributeToKB: edits.contributeToKB ?? true,
      });
      return next;
    });
    setExpandedIndex(null);
  }, []);

  const rejectItem = useCallback((index: number, instruction?: string) => {
    setReviewStates(prev => {
      const next = new Map(prev);
      next.set(index, { decision: 'rejected', instructionUsed: instruction });
      return next;
    });
  }, []);

  const rejectItems = useCallback((indices: number[], instruction?: string) => {
    setReviewStates(prev => {
      const next = new Map(prev);
      for (const idx of indices) {
        next.set(idx, { decision: 'rejected', instructionUsed: instruction });
      }
      return next;
    });
    setSelectedIndices(new Set());
  }, []);

  const reclassifyItems = useCallback((indices: number[], instruction: string) => {
    setReviewStates(prev => {
      const next = new Map(prev);
      for (const idx of indices) {
        next.set(idx, { decision: 'pending', instructionUsed: instruction });
      }
      return next;
    });
    setSelectedIndices(new Set());
  }, []);

  const bulkApprove = useCallback((indices: number[]) => {
    setReviewStates(prev => {
      const next = new Map(prev);
      for (const idx of indices) {
        const existing = next.get(idx) || { decision: 'pending' as ReviewDecision };
        next.set(idx, { ...existing, decision: 'approved', contributeToKB: true });
      }
      return next;
    });
    setSelectedIndices(new Set());
  }, []);

  const bulkApproveHighConfidence = useCallback(() => {
    const highConfItems = items.filter(i => i.confidence >= 0.7 && !reviewStates.get(i.index)?.decision);
    const indices = highConfItems.map(i => i.index);
    bulkApprove(indices);
  }, [items, reviewStates, bulkApprove]);

  const toggleSelection = useCallback((index: number) => {
    setSelectedIndices(prev => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedIndices.size === filteredItems.length) {
      setSelectedIndices(new Set());
    } else {
      setSelectedIndices(new Set(filteredItems.map(i => i.index)));
    }
  }, [selectedIndices.size, filteredItems]);

  const toggleExpanded = useCallback((index: number) => {
    setExpandedIndex(prev => prev === index ? null : index);
  }, []);

  const finalizeReview = useCallback(async () => {
    // Force save
    await saveReviewProgress(sessionId, reviewStates);
    // Build decision list
    const decisions = items.map(item => reviewStates.get(item.index)?.decision || 'approved');
    onComplete?.(decisions);
  }, [sessionId, reviewStates, items, onComplete]);

  const getItemState = useCallback((index: number): ReviewItemState => {
    return reviewStates.get(index) || { decision: 'pending' };
  }, [reviewStates]);

  // Update item after reclassification
  const updateItemAfterReclassify = useCallback((_index: number, _newData: Partial<ClassifiedItem>) => {
    // This is called when reclassifyItems API returns new results.
    // The parent component should update the items array.
    // We just mark it as pending again so reviewer sees the new result.
    setReviewStates(prev => {
      const next = new Map(prev);
      next.set(_index, { decision: 'pending' });
      return next;
    });
  }, []);

  return {
    reviewStates,
    filteredItems,
    filter, setFilter,
    selectedIndices,
    expandedIndex,
    progress,
    filterCounts,
    canFinalize,
    isLoading,
    // Actions
    approveItem,
    editItem,
    rejectItem,
    rejectItems,
    reclassifyItems,
    bulkApprove,
    bulkApproveHighConfidence,
    toggleSelection,
    toggleAll,
    toggleExpanded,
    finalizeReview,
    getItemState,
    updateItemAfterReclassify,
  };
}
