import React from 'react';

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  aiHint?: string;
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  aiHint,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center py-16 text-center ${className}`}>
      {icon && <div className="mb-4 text-primary-300">{icon}</div>}
      <h3 className="text-lg font-medium text-[#32373c] mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-primary-400 max-w-sm mb-2">{description}</p>
      )}
      {aiHint && (
        <p className="text-xs text-ai-400 max-w-xs mb-6 italic">{aiHint}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
