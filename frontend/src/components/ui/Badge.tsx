import React from 'react';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted' | 'accent' | 'ai' | 'mint';
  size?: 'sm' | 'md';
  dot?: boolean;
  dotColor?: string;
  className?: string;
}

export function Badge({ children, variant = 'default', size = 'sm', dot, dotColor, className = '' }: BadgeProps) {
  const variants = {
    default: 'bg-gray-100 text-gray-700',
    success: 'bg-mint-50 text-mint-600',
    warning: 'bg-yellow-100 text-yellow-700',
    danger: 'bg-red-100 text-red-700',
    info: 'bg-accent-50 text-accent-600',
    muted: 'bg-gray-50 text-gray-400',
    accent: 'bg-accent-50 text-accent-600',
    ai: 'bg-ai-50 text-ai-400',
    mint: 'bg-mint-50 text-mint-600',
  };
  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
  };

  const dotColors: Record<string, string> = {
    default: 'bg-gray-400',
    success: 'bg-mint-400',
    warning: 'bg-yellow-400',
    danger: 'bg-red-400',
    info: 'bg-accent-400',
    muted: 'bg-gray-300',
    accent: 'bg-accent-400',
    ai: 'bg-ai-400',
    mint: 'bg-mint-400',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {dot && (
        <span className={`w-1.5 h-1.5 rounded-full ${dotColor || dotColors[variant]}`} />
      )}
      {children}
    </span>
  );
}

/** Renders a confidence percentage as a color-coded badge. */
export function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const variant =
    confidence >= 0.7 ? 'success' : confidence >= 0.45 ? 'warning' : 'danger';
  return <Badge variant={variant}>{pct}%</Badge>;
}

/** Source badge for classification origin */
export function SourceBadge({ source }: { source: string }) {
  const isKB = source.includes('KB') || source.includes('Base') || source.includes('Aprendizado');
  const isAI = source.includes('Grok') || source.includes('LLM');
  return (
    <Badge variant={isKB ? 'accent' : isAI ? 'ai' : 'muted'} dot>
      {source}
    </Badge>
  );
}
