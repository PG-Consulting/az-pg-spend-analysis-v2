import React from 'react';

interface ChatLockedProps {
  reason?: string;
}

export function ChatLocked({ reason = 'Complete a revisão para desbloquear a análise conversacional.' }: ChatLockedProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[300px] py-12 px-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
        <svg className="w-8 h-8 text-primary-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-[#32373c] mb-2">Analise bloqueada</h3>
      <p className="text-sm text-primary-400 max-w-xs">{reason}</p>
    </div>
  );
}
