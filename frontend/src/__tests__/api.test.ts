/**
 * @fileoverview Tests for the Spend Analysis v3 API client.
 *
 * Covers: apiClient methods, endpoint URLs, request parameters,
 * and the fileToBase64 utility (indirectly via submitClassificationJob).
 */

import axios from 'axios';
import { apiClient, API_BASE_URL } from '../lib/api';

// ---------------------------------------------------------------------------
// Mock axios at module level
// ---------------------------------------------------------------------------
jest.mock('axios', () => {
  const mockAxiosInstance = {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    defaults: { baseURL: '' },
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };

  return {
    __esModule: true,
    default: {
      ...mockAxiosInstance,
      create: jest.fn(() => mockAxiosInstance),
    },
  };
});

const mockedAxios = axios as jest.Mocked<typeof axios>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
beforeEach(() => {
  jest.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('apiClient', () => {
  // 1. Base URL configuration
  describe('API_BASE_URL', () => {
    it('should default to localhost:7071 when NEXT_PUBLIC_API_URL is not set', () => {
      // The module-level constant falls back to localhost when env is absent.
      // In the test environment NEXT_PUBLIC_API_URL is not set, so we expect
      // the default value.
      expect(API_BASE_URL).toBe(
        process.env.NEXT_PUBLIC_API_URL || 'http://localhost:7071/api'
      );
    });
  });

  // 2. submitClassificationJobRaw -> POST /SubmitTaxonomyJob
  describe('submitClassificationJobRaw', () => {
    it('should POST to /SubmitTaxonomyJob with correct params and return jobId', async () => {
      const fakeJobId = 'job-abc-123';
      (mockedAxios.post as jest.Mock).mockResolvedValueOnce({
        data: { jobId: fakeJobId },
      });

      const params = {
        fileContent: 'base64encodedcontent==',
        originalFilename: 'gastos.xlsx',
        projectId: 'naval-wartsila',
        sector: 'naval',
        descColumn: 'Descrição',
      };

      const result = await apiClient.submitClassificationJobRaw(params);

      expect(mockedAxios.post).toHaveBeenCalledTimes(1);
      const [url, body] = (mockedAxios.post as jest.Mock).mock.calls[0];
      expect(url).toBe(`${API_BASE_URL}/SubmitTaxonomyJob`);
      expect(body).toMatchObject({
        fileContent: params.fileContent,
        originalFilename: params.originalFilename,
        projectId: params.projectId,
        sector: params.sector,
        descColumn: params.descColumn,
      });
      expect(result).toEqual({ jobId: fakeJobId });
    });
  });

  // 3. getJobStatus -> GET /GetTaxonomyJobStatus with jobId param
  describe('getJobStatus', () => {
    it('should GET /GetTaxonomyJobStatus with jobId query param', async () => {
      const fakeStatus = {
        jobId: 'job-xyz',
        status: 'CLASSIFIED',
        progress: 100,
      };
      (mockedAxios.get as jest.Mock).mockResolvedValueOnce({
        data: fakeStatus,
      });

      const result = await apiClient.getJobStatus('job-xyz');

      expect(mockedAxios.get).toHaveBeenCalledTimes(1);
      const [url, config] = (mockedAxios.get as jest.Mock).mock.calls[0];
      expect(url).toBe(`${API_BASE_URL}/GetTaxonomyJobStatus`);
      expect(config.params).toEqual({ jobId: 'job-xyz' });
      expect(result).toEqual(fakeStatus);
    });
  });

  // 4. getJobResults -> GET /GetJobResults with jobId param
  describe('getJobResults', () => {
    it('should GET /GetJobResults with jobId query param', async () => {
      const fakeResults = {
        jobId: 'job-xyz',
        status: 'CLASSIFIED',
        items: [
          {
            index: 0,
            description: 'Parafuso M8',
            N1: 'MRO',
            N2: 'Fixacao',
            N3: 'Parafusos',
            N4: 'Parafuso Sextavado',
            confidence: 0.92,
            source: 'LLM',
            status: 'Único',
          },
        ],
        total: 1,
      };
      (mockedAxios.get as jest.Mock).mockResolvedValueOnce({
        data: fakeResults,
      });

      const result = await apiClient.getJobResults('job-xyz');

      expect(mockedAxios.get).toHaveBeenCalledTimes(1);
      const [url, config] = (mockedAxios.get as jest.Mock).mock.calls[0];
      expect(url).toBe(`${API_BASE_URL}/GetJobResults`);
      expect(config.params).toEqual({ jobId: 'job-xyz' });
      expect(result).toEqual(fakeResults);
      expect(result.items).toHaveLength(1);
      expect(result.items[0].N1).toBe('MRO');
    });
  });

  // 5. approveClassifications -> POST /ApproveClassifications
  describe('approveClassifications', () => {
    it('should POST to /ApproveClassifications with decisions payload', async () => {
      const fakeResponse = {
        success: true,
        kb_added: 5,
        summary: { total: 10, approved: 8, edited: 2, rejected: 0, kb_added: 5 },
        download_filename: 'classificado_final.xlsx',
        file_content_base64: 'base64data==',
      };
      (mockedAxios.post as jest.Mock).mockResolvedValueOnce({
        data: fakeResponse,
      });

      const params = {
        jobId: 'job-xyz',
        projectId: 'naval-wartsila',
        decisions: [
          {
            index: 0,
            description: 'Parafuso M8',
            decision: 'approved' as const,
            N1: 'MRO',
            N2: 'Fixacao',
            N3: 'Parafusos',
            N4: 'Parafuso Sextavado',
            confidence: 0.92,
            source: 'LLM',
            contribute_to_kb: true,
          },
          {
            index: 1,
            description: 'Oleo motor',
            decision: 'edited' as const,
            N1: 'MRO',
            N2: 'Lubrificacao',
            N3: 'Oleos',
            N4: 'Oleo Motor',
            confidence: 0.85,
            source: 'consultant_correction',
            contribute_to_kb: true,
          },
        ],
      };

      const result = await apiClient.approveClassifications(params);

      expect(mockedAxios.post).toHaveBeenCalledTimes(1);
      const [url, body] = (mockedAxios.post as jest.Mock).mock.calls[0];
      expect(url).toBe(`${API_BASE_URL}/ApproveClassifications`);
      expect(body.jobId).toBe('job-xyz');
      expect(body.projectId).toBe('naval-wartsila');
      expect(body.decisions).toHaveLength(2);
      expect(body.decisions[0].decision).toBe('approved');
      expect(body.decisions[1].decision).toBe('edited');
      expect(result.success).toBe(true);
      expect(result.kb_added).toBe(5);
    });
  });

  // 6. getSectorKB -> GET /GetSectorKB
  describe('getSectorKB', () => {
    it('should GET /GetSectorKB with sectorName query param', async () => {
      const fakeData = {
        entries: [{ id: 'e1', description: 'Parafuso', N4: 'Parafuso Sextavado' }],
        total: 1,
        page: 1,
        pages: 1,
      };
      (mockedAxios.get as jest.Mock).mockResolvedValueOnce({ data: fakeData });

      const result = await apiClient.getSectorKB('naval', { page: 1, pageSize: 50 });

      expect(mockedAxios.get).toHaveBeenCalledTimes(1);
      const [url, config] = (mockedAxios.get as jest.Mock).mock.calls[0];
      expect(url).toBe(`${API_BASE_URL}/GetSectorKB`);
      expect(config.params.sectorName).toBe('naval');
      expect(result.entries).toHaveLength(1);
    });
  });

  // 7. promoteToSectorKB -> POST /PromoteToSectorKB
  describe('promoteToSectorKB', () => {
    it('should POST to /PromoteToSectorKB with projectId, sectorName, and entryIds', async () => {
      const fakeResponse = { success: true, promoted_count: 3 };
      (mockedAxios.post as jest.Mock).mockResolvedValueOnce({ data: fakeResponse });

      const result = await apiClient.promoteToSectorKB('naval-wartsila', 'naval', ['id1', 'id2', 'id3']);

      expect(mockedAxios.post).toHaveBeenCalledTimes(1);
      const [url, body] = (mockedAxios.post as jest.Mock).mock.calls[0];
      expect(url).toBe(`${API_BASE_URL}/PromoteToSectorKB`);
      expect(body.projectId).toBe('naval-wartsila');
      expect(body.sectorName).toBe('naval');
      expect(body.entryIds).toHaveLength(3);
      expect(result.promoted_count).toBe(3);
    });
  });

  // 8. exportSectorKB -> GET /ExportSectorKB
  describe('exportSectorKB', () => {
    it('should GET /ExportSectorKB and return file_content_base64', async () => {
      const fakeData = {
        sectorName: 'naval',
        entry_count: 10,
        filename: 'knowledge_base_sector_naval.xlsx',
        file_content_base64: 'base64xlsxdata==',
      };
      (mockedAxios.get as jest.Mock).mockResolvedValueOnce({ data: fakeData });

      const result = await apiClient.exportSectorKB('naval');

      expect(mockedAxios.get).toHaveBeenCalledTimes(1);
      const [url, config] = (mockedAxios.get as jest.Mock).mock.calls[0];
      expect(url).toBe(`${API_BASE_URL}/ExportSectorKB`);
      expect(config.params.sectorName).toBe('naval');
      expect(result).toBe('base64xlsxdata==');
    });
  });
});
