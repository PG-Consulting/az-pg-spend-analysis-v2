import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface SlideOverProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  /** Default width in pixels */
  defaultWidth?: number;
  /** Minimum width in pixels (only used when resizable) */
  minWidth?: number;
  /** Maximum width in pixels (only used when resizable) */
  maxWidth?: number;
  /** Enable drag-to-resize on the left edge */
  resizable?: boolean;
  /** localStorage key to persist the resized width */
  storageKey?: string;
  children: React.ReactNode;
}

export function SlideOver({
  isOpen,
  onClose,
  title,
  subtitle,
  defaultWidth = 480,
  minWidth = 400,
  maxWidth,
  resizable = false,
  storageKey,
  children,
}: SlideOverProps) {
  const backdropRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [dragging, setDragging] = useState(false);

  // Resolve initial width from localStorage or defaultWidth
  const [panelWidth, setPanelWidth] = useState(defaultWidth);

  useEffect(() => {
    if (storageKey) {
      const stored = localStorage.getItem(`slideover-width-${storageKey}`);
      if (stored) {
        const parsed = parseInt(stored, 10);
        if (!isNaN(parsed) && parsed >= minWidth) {
          setPanelWidth(parsed);
        }
      }
    }
  }, [storageKey, minWidth]);

  // Persist width to localStorage on change
  useEffect(() => {
    if (storageKey && panelWidth !== defaultWidth) {
      localStorage.setItem(`slideover-width-${storageKey}`, String(panelWidth));
    }
  }, [panelWidth, storageKey, defaultWidth]);

  // Compute effective max width
  const getMaxWidth = useCallback(() => {
    if (maxWidth) return maxWidth;
    if (typeof window !== 'undefined') return Math.floor(window.innerWidth * 0.92);
    return 1400;
  }, [maxWidth]);

  // Mount/unmount with transition support
  useEffect(() => {
    if (isOpen) {
      setMounted(true);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setVisible(true);
        });
      });
    } else {
      setVisible(false);
      const timer = setTimeout(() => setMounted(false), 300);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Close on Escape key + lock body scroll
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  // Drag-to-resize handlers
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!resizable) return;
    e.preventDefault();
    setDragging(true);
  }, [resizable]);

  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = window.innerWidth - e.clientX;
      const clamped = Math.max(minWidth, Math.min(newWidth, getMaxWidth()));
      setPanelWidth(clamped);
    };

    const handleMouseUp = () => {
      setDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    // Prevent text selection while dragging
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [dragging, minWidth, getMaxWidth]);

  // Close on backdrop click
  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === backdropRef.current) onClose();
  };

  // Double-click on handle resets to default width
  const handleDoubleClick = useCallback(() => {
    setPanelWidth(defaultWidth);
    if (storageKey) {
      localStorage.removeItem(`slideover-width-${storageKey}`);
    }
  }, [defaultWidth, storageKey]);

  if (!mounted) return null;

  const content = (
    <>
      {/* Backdrop */}
      <div
        ref={backdropRef}
        onClick={handleBackdropClick}
        className={`fixed inset-0 z-40 bg-black/20 backdrop-blur-sm transition-opacity duration-300 ${
          visible ? 'opacity-100' : 'opacity-0'
        }`}
      />

      {/* Panel */}
      <div
        className={`fixed right-0 top-0 bottom-0 z-50 bg-white shadow-2xl flex flex-col ease-out ${
          dragging ? '' : 'transition-transform duration-300'
        } ${
          visible ? 'translate-x-0' : 'translate-x-full'
        }`}
        style={{ width: Math.min(panelWidth, getMaxWidth()), maxWidth: '100vw' }}
      >
        {/* Resize handle */}
        {resizable && (
          <div
            onMouseDown={handleMouseDown}
            onDoubleClick={handleDoubleClick}
            className={`absolute left-0 top-0 bottom-0 w-1.5 z-10 cursor-col-resize group ${
              dragging ? 'bg-[#0693e3]' : 'hover:bg-[#0693e3]/40'
            } transition-colors`}
            title="Arraste para redimensionar (duplo-clique para resetar)"
          >
            {/* Visual grip dots */}
            <div className={`absolute top-1/2 -translate-y-1/2 left-0 w-1.5 flex flex-col items-center gap-1 py-2 ${
              dragging ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
            } transition-opacity`}>
              <div className="w-0.5 h-0.5 rounded-full bg-[#0693e3]" />
              <div className="w-0.5 h-0.5 rounded-full bg-[#0693e3]" />
              <div className="w-0.5 h-0.5 rounded-full bg-[#0693e3]" />
              <div className="w-0.5 h-0.5 rounded-full bg-[#0693e3]" />
              <div className="w-0.5 h-0.5 rounded-full bg-[#0693e3]" />
            </div>
          </div>
        )}

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-[#32373c] truncate">{title}</h2>
            {subtitle && (
              <p className="text-sm text-gray-500 mt-0.5 truncate">{subtitle}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-4 flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors p-1.5 rounded-lg hover:bg-gray-100"
            aria-label="Fechar"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </>
  );

  return typeof window !== 'undefined' ? createPortal(content, document.body) : null;
}
