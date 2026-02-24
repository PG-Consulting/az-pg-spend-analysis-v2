import { useMemo } from 'react';
import type { HierarchyEntry, HierarchyTree } from '../lib/types';

export function useHierarchy(hierarchyEntries: HierarchyEntry[] | null | undefined) {
  // Build tree structure: N1 -> N2 -> N3 -> N4[]
  const tree = useMemo<HierarchyTree>(() => {
    if (!hierarchyEntries || hierarchyEntries.length === 0) return {};

    const result: HierarchyTree = {};
    for (const entry of hierarchyEntries) {
      const n1 = entry.N1?.trim() || '';
      const n2 = entry.N2?.trim() || '';
      const n3 = entry.N3?.trim() || '';
      const n4 = entry.N4?.trim() || '';
      if (!n1) continue;
      if (!result[n1]) result[n1] = {};
      if (!result[n1][n2]) result[n1][n2] = {};
      if (!result[n1][n2][n3]) result[n1][n2][n3] = [];
      if (n4 && !result[n1][n2][n3].includes(n4)) {
        result[n1][n2][n3].push(n4);
      }
    }
    return result;
  }, [hierarchyEntries]);

  const n1Options = useMemo(() => Object.keys(tree).sort(), [tree]);

  const getN2Options = (n1: string) => {
    if (!n1 || !tree[n1]) return [];
    return Object.keys(tree[n1]).sort();
  };

  const getN3Options = (n1: string, n2: string) => {
    if (!n1 || !n2 || !tree[n1]?.[n2]) return [];
    return Object.keys(tree[n1][n2]).sort();
  };

  const getN4Options = (n1: string, n2: string, n3: string) => {
    if (!n1 || !n2 || !n3 || !tree[n1]?.[n2]?.[n3]) return [];
    return tree[n1][n2][n3].sort();
  };

  const isValidPath = (n1: string, n2: string, n3: string, n4: string) => {
    return !!tree[n1]?.[n2]?.[n3]?.includes(n4);
  };

  const hasHierarchy = hierarchyEntries && hierarchyEntries.length > 0;

  return { tree, n1Options, getN2Options, getN3Options, getN4Options, isValidPath, hasHierarchy };
}
