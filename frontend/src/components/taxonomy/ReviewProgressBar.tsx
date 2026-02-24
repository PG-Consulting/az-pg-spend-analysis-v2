import React from 'react';

interface ReviewProgressBarProps {
  reviewed: number;
  total: number;
  approved: number;
  edited: number;
  rejected: number;
}

export function ReviewProgressBar({ reviewed, total, approved, edited, rejected }: ReviewProgressBarProps) {
  const pct = total > 0 ? Math.round((reviewed / total) * 100) : 0;
  const approvedPct = total > 0 ? (approved / total) * 100 : 0;
  const editedPct = total > 0 ? (edited / total) * 100 : 0;
  const rejectedPct = total > 0 ? (rejected / total) * 100 : 0;

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-gray-700">
          {reviewed.toLocaleString()} / {total.toLocaleString()} revisados
        </span>
        <span className={`font-bold ${pct === 100 ? 'text-green-600' : 'text-[#0693e3]'}`}>{pct}%</span>
      </div>

      {/* Segmented progress bar */}
      <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden flex">
        <div className="h-full bg-green-500 transition-all duration-300" style={{ width: `${approvedPct}%` }} title={`Aprovados: ${approved}`} />
        <div className="h-full bg-[#0693e3] transition-all duration-300" style={{ width: `${editedPct}%` }} title={`Editados: ${edited}`} />
        <div className="h-full bg-red-400 transition-all duration-300" style={{ width: `${rejectedPct}%` }} title={`Rejeitados: ${rejected}`} />
      </div>

      {/* Legend */}
      <div className="flex gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block" />{approved} aprovados</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#0693e3] inline-block" />{edited} editados</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400 inline-block" />{rejected} rejeitados</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-gray-300 inline-block" />{total - reviewed} pendentes</span>
      </div>
    </div>
  );
}
