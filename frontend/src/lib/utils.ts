/**
 * @fileoverview Shared utility functions for the Spend Analysis frontend.
 */

/**
 * Converts a raw classification source string into a user-friendly label.
 *
 * @param source - The classification source identifier (e.g. "KB (Direct Match)", "LLM (Batch)")
 * @returns A human-readable label for display in the UI
 */
export function getSourceLabel(source: string): string {
  if (source === 'KB (Direct Match)') return 'Base de Aprendizado';
  if (source.startsWith('LLM')) return 'Grok';
  if (source === 'Taxonomy (Dict)') return 'Dicionário';
  if (source === 'ML') return 'ML';
  return source || '--';
}
