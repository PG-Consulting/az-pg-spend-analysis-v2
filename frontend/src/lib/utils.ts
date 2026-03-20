/**
 * @fileoverview Shared utility functions for the Spend.AI frontend.
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
  if (source === 'consultant_correction') return 'Ajuste Manual';
  if (source === 'reclassified_with_guidance') return 'Reclassificado';
  return source || '--';
}

/**
 * Decodes a base64 string and triggers a browser file download.
 *
 * @param base64 - The base64-encoded file content
 * @param filename - The filename to use for the download
 * @param mimeType - The MIME type of the file (defaults to Excel .xlsx)
 */
export function downloadBase64AsFile(
  base64: string,
  filename: string,
  mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
) {
  const byteCharacters = atob(base64);
  const byteNumbers = new Uint8Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  const blob = new Blob([byteNumbers], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
