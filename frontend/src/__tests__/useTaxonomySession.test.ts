/**
 * @fileoverview Tests for the useTaxonomySession hook (Spend Analysis v3).
 *
 * The hook manages taxonomy classification sessions: submitting jobs,
 * polling for status, storing results in IndexedDB, and managing
 * session lifecycle (create, delete, clear).
 *
 * We test the hook via @testing-library/react renderHook, mocking
 * IndexedDB persistence and the API client.
 */

import { renderHook, act } from '@testing-library/react';
import { useTaxonomySession } from '../hooks/useTaxonomySession';
import type { TaxonomySession, ReviewSummary } from '../lib/types';

// ---------------------------------------------------------------------------
// Mock IndexedDB persistence layer
// ---------------------------------------------------------------------------
jest.mock('../lib/database', () => ({
  saveSession: jest.fn().mockResolvedValue(undefined),
  getAllSessions: jest.fn().mockResolvedValue([]),
  clearAllSessions: jest.fn().mockResolvedValue(undefined),
  deleteSession: jest.fn().mockResolvedValue(undefined),
}));

// ---------------------------------------------------------------------------
// Mock API client
// ---------------------------------------------------------------------------
jest.mock('../lib/api', () => ({
  apiClient: {
    submitClassificationJobRaw: jest.fn(),
    getJobStatus: jest.fn(),
    getJobResults: jest.fn(),
    cancelJob: jest.fn(),
  },
}));

// Import mocked modules for assertions
import { saveSession, getAllSessions, clearAllSessions, deleteSession } from '../lib/database';
import { apiClient } from '../lib/api';

// ---------------------------------------------------------------------------
// Suppress console output during tests
// ---------------------------------------------------------------------------
const originalConsoleLog = console.log;
const originalConsoleWarn = console.warn;
const originalConsoleError = console.error;

beforeEach(() => {
  console.log = jest.fn();
  console.warn = jest.fn();
  console.error = jest.fn();
  jest.clearAllMocks();
});

afterEach(() => {
  console.log = originalConsoleLog;
  console.warn = originalConsoleWarn;
  console.error = originalConsoleError;
  localStorage.clear();
  jest.useRealTimers();
});

// ---------------------------------------------------------------------------
// Helper: flush microtasks / async effects (real timers only)
// ---------------------------------------------------------------------------
const flushAsync = () => act(async () => {
  await new Promise(r => setTimeout(r, 10));
});

// ---------------------------------------------------------------------------
// Test data factory
// ---------------------------------------------------------------------------
function createMockSession(overrides: Partial<TaxonomySession> = {}): TaxonomySession {
  return {
    sessionId: 'session-001',
    jobId: 'job-001',
    filename: 'compras.xlsx',
    timestamp: Date.now(),
    jobStatus: 'CLASSIFIED',
    summary: { total: 50 },
    analytics: {},
    items: [
      {
        index: 0,
        description: 'Parafuso M8',
        N1: 'MRO',
        N2: 'Fixacao',
        N3: 'Parafusos',
        N4: 'Parafuso Sextavado',
        confidence: 0.9,
        source: 'LLM',
        status: 'Único',
      },
    ],
    reviewState: 'pending',
    reviewedCount: 0,
    totalItems: 50,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('useTaxonomySession', () => {
  // 1. Initial state
  it('should start with empty sessions and no active session when getAllSessions returns []', async () => {
    (getAllSessions as jest.Mock).mockResolvedValue([]);

    const { result } = renderHook(() => useTaxonomySession());

    await flushAsync();

    expect(result.current.sessions).toEqual([]);
    expect(result.current.activeSessionId).toBeNull();
    expect(result.current.activeSession).toBeUndefined();
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.isCancelling).toBe(false);
    expect(result.current.progress).toBeNull();
    expect(result.current.clientContext).toBe('');
    expect(result.current.activeProjectId).toBeNull();
  });

  // 2. Loads sessions from IndexedDB
  it('should load sessions from IndexedDB and set first as active', async () => {
    const session1 = createMockSession({ sessionId: 'session-001', jobId: 'job-001', timestamp: 1000 });
    const session2 = createMockSession({ sessionId: 'session-002', jobId: 'job-002', timestamp: 2000 });
    (getAllSessions as jest.Mock).mockResolvedValue([session1, session2]);

    const { result } = renderHook(() => useTaxonomySession());

    await flushAsync();

    expect(result.current.sessions).toHaveLength(2);
    expect(result.current.activeSessionId).toBe('session-001');
    expect(result.current.activeSession).toEqual(session1);
  });

  // 3. handleNewUpload
  it('should set activeSessionId to null when handleNewUpload is called', async () => {
    const session = createMockSession();
    (getAllSessions as jest.Mock).mockResolvedValue([session]);

    const { result } = renderHook(() => useTaxonomySession());

    await flushAsync();

    expect(result.current.activeSessionId).toBe('session-001');

    act(() => {
      result.current.handleNewUpload();
    });

    expect(result.current.activeSessionId).toBeNull();
    expect(result.current.activeSession).toBeUndefined();
  });

  // 4. handleFileSelect — success flow
  it('should submit job, poll status, fetch results and create session on success', async () => {
    jest.useFakeTimers();

    (getAllSessions as jest.Mock).mockResolvedValue([]);

    const jobId = 'job-new-001';
    const mockFile = new File(['test'], 'test.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const fileContent = 'base64content';

    (apiClient.submitClassificationJobRaw as jest.Mock).mockResolvedValue({ jobId });

    (apiClient.getJobStatus as jest.Mock)
      .mockResolvedValueOnce({
        jobId,
        status: 'PROCESSING',
        progress_pct: 50,
        message: 'Classificando chunks...',
      })
      .mockResolvedValueOnce({
        jobId,
        status: 'CLASSIFIED',
        progress_pct: 100,
        message: 'Concluido',
        download_filename: 'result.xlsx',
        file_content_base64: 'abc123',
      });

    (apiClient.getJobResults as jest.Mock).mockResolvedValue({
      jobId,
      status: 'CLASSIFIED',
      items: [
        {
          index: 0,
          description: 'Parafuso M8',
          N1: 'MRO',
          N2: 'Fixacao',
          N3: 'Parafusos',
          N4: 'Parafuso Sextavado',
          confidence: 0.9,
          source: 'LLM',
          status: 'Único',
        },
      ],
      total: 1,
      summary: { total: 1 },
      analytics: { n1_distribution: {} },
    });

    const { result } = renderHook(() => useTaxonomySession());

    // Flush initial useEffect
    await act(async () => { await jest.advanceTimersByTimeAsync(50); });

    // Start handleFileSelect
    let fileSelectPromise: Promise<void>;
    await act(async () => {
      fileSelectPromise = result.current.handleFileSelect(mockFile, fileContent);
    });

    expect(result.current.isProcessing).toBe(true);

    // Advance past first 5s poll -> PROCESSING
    await act(async () => { await jest.advanceTimersByTimeAsync(5000); });

    // Advance past second 5s poll -> CLASSIFIED -> getJobResults -> save
    await act(async () => { await jest.advanceTimersByTimeAsync(5000); });

    // Wait for the full flow to finish
    await act(async () => { await fileSelectPromise!; });

    expect(apiClient.submitClassificationJobRaw).toHaveBeenCalledWith({
      fileContent: 'base64content',
      originalFilename: 'test.xlsx',
      projectId: undefined,
      customHierarchy: undefined,
    });
    expect(apiClient.getJobStatus).toHaveBeenCalledTimes(2);
    expect(apiClient.getJobResults).toHaveBeenCalledWith(jobId);
    expect(saveSession).toHaveBeenCalled();

    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].sessionId).toBe(jobId);
    expect(result.current.sessions[0].jobStatus).toBe('CLASSIFIED');
    expect(result.current.activeSessionId).toBe(jobId);
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.progress).toBeNull();
  }, 15000);

  // 5. handleFileSelect — submission error
  // Tests the error path when submitClassificationJobRaw itself rejects.
  it('should show error alert when job submission fails', async () => {
    (getAllSessions as jest.Mock).mockResolvedValue([]);

    (apiClient.submitClassificationJobRaw as jest.Mock).mockRejectedValue(
      new Error('Network error')
    );

    const alertMock = jest.fn();
    window.alert = alertMock;

    const mockFile = new File(['test'], 'test.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    const { result } = renderHook(() => useTaxonomySession());

    await flushAsync();

    await act(async () => {
      await result.current.handleFileSelect(mockFile, 'base64content');
    });

    expect(alertMock).toHaveBeenCalledWith(
      expect.stringContaining('Network error')
    );
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.progress).toBeNull();
    expect(result.current.sessions).toHaveLength(0);
  });

  // 6. handleFileSelect — 404 during polling
  // When getJobStatus rejects with response.status=404, the error propagates
  // to the outer catch and shows an alert.
  it('should show error when polling returns 404 (job not found)', async () => {
    jest.useFakeTimers();

    (getAllSessions as jest.Mock).mockResolvedValue([]);

    const jobId = 'job-404';
    const mockFile = new File(['test'], 'test.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    (apiClient.submitClassificationJobRaw as jest.Mock).mockResolvedValue({ jobId });

    // Simulate a 404 response from getJobStatus
    const err404 = new Error('Not Found') as any;
    err404.response = { status: 404 };
    (apiClient.getJobStatus as jest.Mock).mockRejectedValueOnce(err404);

    const alertMock = jest.fn();
    window.alert = alertMock;

    const { result } = renderHook(() => useTaxonomySession());

    // Flush initial load
    await act(async () => { await jest.advanceTimersByTimeAsync(50); });

    let fileSelectPromise: Promise<void>;
    await act(async () => {
      fileSelectPromise = result.current.handleFileSelect(mockFile, 'base64content');
    });

    // Advance past the 5s poll -> 404 -> throw -> outer catch -> alert
    await act(async () => { await jest.advanceTimersByTimeAsync(5000); });

    await act(async () => { await fileSelectPromise!; });

    expect(alertMock).toHaveBeenCalledWith(
      expect.stringContaining('Job n\u00e3o encontrado')
    );
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.sessions).toHaveLength(0);
  }, 15000);

  // 7. cancelJob
  it('should call apiClient.cancelJob and set isCancelling', async () => {
    jest.useFakeTimers();

    (getAllSessions as jest.Mock).mockResolvedValue([]);

    const jobId = 'job-cancel-001';
    const mockFile = new File(['test'], 'test.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    (apiClient.submitClassificationJobRaw as jest.Mock).mockResolvedValue({ jobId });
    (apiClient.cancelJob as jest.Mock).mockResolvedValue(undefined);
    (apiClient.getJobStatus as jest.Mock).mockResolvedValue({
      jobId,
      status: 'CANCELLED',
    });

    const { result } = renderHook(() => useTaxonomySession());

    // Flush initial load
    await act(async () => { await jest.advanceTimersByTimeAsync(50); });

    // Start file processing
    let fileSelectPromise: Promise<void>;
    await act(async () => {
      fileSelectPromise = result.current.handleFileSelect(mockFile, 'base64content');
    });

    expect(result.current.isProcessing).toBe(true);

    // Cancel the job before the first poll fires
    await act(async () => {
      await result.current.cancelJob();
    });

    expect(apiClient.cancelJob).toHaveBeenCalledWith(jobId);
    expect(result.current.isCancelling).toBe(true);

    // Advance timer so the polling loop encounters cancelledRef=true and returns
    await act(async () => { await jest.advanceTimersByTimeAsync(5000); });

    await act(async () => { await fileSelectPromise!; });

    expect(result.current.isProcessing).toBe(false);
  }, 15000);

  // 8. setReviewCompleted
  it('should update active session with reviewState completed and summary data', async () => {
    const session = createMockSession({ sessionId: 'session-review', jobId: 'job-review' });
    (getAllSessions as jest.Mock).mockResolvedValue([session]);

    const { result } = renderHook(() => useTaxonomySession());

    await flushAsync();

    expect(result.current.activeSessionId).toBe('session-review');
    expect(result.current.activeSession?.reviewState).toBe('pending');

    const summary: ReviewSummary = {
      total: 50,
      approved: 40,
      edited: 8,
      rejected: 2,
      kb_added: 35,
    };

    await act(async () => {
      await result.current.setReviewCompleted(summary, 'approvedB64Data', 'approved_result.xlsx');
    });

    expect(result.current.activeSession?.reviewState).toBe('completed');
    expect(result.current.activeSession?.reviewSummary).toEqual(summary);
    expect(result.current.activeSession?.approvedFileContentBase64).toBe('approvedB64Data');
    expect(result.current.activeSession?.approvedDownloadFilename).toBe('approved_result.xlsx');
    expect(saveSession).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: 'session-review',
        reviewState: 'completed',
        reviewSummary: summary,
        approvedFileContentBase64: 'approvedB64Data',
        approvedDownloadFilename: 'approved_result.xlsx',
      })
    );
  });

  // 9. handleDeleteSession
  it('should remove session from state and call deleteSession on database', async () => {
    const session1 = createMockSession({ sessionId: 'session-del-1', jobId: 'job-del-1' });
    const session2 = createMockSession({ sessionId: 'session-del-2', jobId: 'job-del-2' });
    (getAllSessions as jest.Mock).mockResolvedValue([session1, session2]);

    localStorage.setItem('pg_spend_chat_session-del-1', 'some-chat-data');

    const { result } = renderHook(() => useTaxonomySession());

    await flushAsync();

    expect(result.current.sessions).toHaveLength(2);
    expect(result.current.activeSessionId).toBe('session-del-1');

    await act(async () => {
      await result.current.handleDeleteSession('session-del-1');
    });

    expect(deleteSession).toHaveBeenCalledWith('session-del-1');
    expect(localStorage.getItem('pg_spend_chat_session-del-1')).toBeNull();
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].sessionId).toBe('session-del-2');
    expect(result.current.activeSessionId).toBeNull();
  });

  // 10. handleClearHistory
  it('should clear all sessions and localStorage chat keys', async () => {
    const session1 = createMockSession({ sessionId: 'session-clr-1' });
    const session2 = createMockSession({ sessionId: 'session-clr-2' });
    (getAllSessions as jest.Mock).mockResolvedValue([session1, session2]);

    localStorage.setItem('pg_spend_chat_session-clr-1', 'chat-data-1');
    localStorage.setItem('pg_spend_chat_session-clr-2', 'chat-data-2');
    localStorage.setItem('other_key', 'should-remain');

    const { result } = renderHook(() => useTaxonomySession());

    await flushAsync();

    expect(result.current.sessions).toHaveLength(2);

    await act(async () => {
      await result.current.handleClearHistory();
    });

    expect(clearAllSessions).toHaveBeenCalled();
    expect(result.current.sessions).toEqual([]);
    expect(result.current.activeSessionId).toBeNull();
    expect(localStorage.getItem('pg_spend_chat_session-clr-1')).toBeNull();
    expect(localStorage.getItem('pg_spend_chat_session-clr-2')).toBeNull();
    expect(localStorage.getItem('other_key')).toBe('should-remain');
  });
});
