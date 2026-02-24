import React from 'react';

interface ProgressBarProps {
  value: number;
  max?: number;
  label?: string;
  showPercent?: boolean;
  color?: 'accent' | 'mint' | 'ai-gradient' | 'green' | 'yellow' | 'red';
  size?: 'thin' | 'sm' | 'md' | 'lg';
  className?: string;
}

export function ProgressBar({
  value,
  max = 100,
  label,
  showPercent = true,
  color = 'accent',
  size = 'md',
  className = '',
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));

  const colorMap: Record<string, string> = {
    accent: 'bg-accent-500',
    mint: 'bg-mint-400',
    'ai-gradient': 'bg-gradient-to-r from-[#0693e3] to-[#9b51e0]',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
  };

  const heights = {
    thin: 'h-1',
    sm: 'h-1.5',
    md: 'h-2',
    lg: 'h-3',
  };

  return (
    <div className={`w-full ${className}`}>
      {(label || showPercent) && (
        <div className="flex justify-between mb-1 text-sm text-gray-600">
          {label && <span>{label}</span>}
          {showPercent && <span>{Math.round(pct)}%</span>}
        </div>
      )}
      <div className={`w-full bg-gray-100 rounded-full ${heights[size]} overflow-hidden`}>
        <div
          className={`${colorMap[color]} ${heights[size]} rounded-full transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)]`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
