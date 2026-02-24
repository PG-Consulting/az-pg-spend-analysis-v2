import { useState, useCallback, useMemo, useRef } from 'react';

interface UseVirtualScrollOptions {
  items: any[];
  rowHeight: number;
  containerHeight: number;
  overscan?: number; // extra rows to render above/below visible area
}

interface UseVirtualScrollResult {
  visibleItems: Array<{ item: any; index: number; top: number }>;
  totalHeight: number;
  scrollTop: number;
  onScroll: (e: React.UIEvent<HTMLDivElement>) => void;
  containerRef: React.RefObject<HTMLDivElement>;
}

export function useVirtualScroll({
  items,
  rowHeight,
  containerHeight,
  overscan = 5,
}: UseVirtualScrollOptions): UseVirtualScrollResult {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const totalHeight = items.length * rowHeight;

  const visibleItems = useMemo(() => {
    const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const endIndex = Math.min(
      items.length - 1,
      Math.ceil((scrollTop + containerHeight) / rowHeight) + overscan
    );

    const result = [];
    for (let i = startIndex; i <= endIndex; i++) {
      result.push({
        item: items[i],
        index: i,
        top: i * rowHeight,
      });
    }
    return result;
  }, [items, scrollTop, rowHeight, containerHeight, overscan]);

  const onScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  return { visibleItems, totalHeight, scrollTop, onScroll, containerRef };
}
