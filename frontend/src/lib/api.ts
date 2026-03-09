/**
 * @fileoverview HTTP API client for Spend Analysis v3.
 *
 * Extends v2 with project-aware classification, review workflow,
 * knowledge base management, and sector/project CRUD endpoints.
 *
 * Backward-compatible: v2 methods (trainModel, getModelHistory, etc.)
 * are preserved unchanged.
 */

import axios from 'axios';
import type {
  Project,
  Sector,
  HierarchyEntry,
  ClassifiedItem,
  ReviewDecision,
  ReviewSummary,
  JobStatusResponse,
  KBEntry,
  KBPage,
  KBCoverage,
  KBVersion,
} from './types';

/** Base URL for the Azure Functions API (configurable via environment) */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:7071/api';

/** Function key for Azure Functions authentication (optional, for production) */
const FUNCTION_KEY = process.env.NEXT_PUBLIC_FUNCTION_KEY || '';

/**
 * Generates authentication headers for Azure Functions requests.
 * Only includes the x-functions-key header when a key is configured.
 */
const getAuthHeaders = (): Record<string, string> => {
  if (FUNCTION_KEY) {
    return { 'x-functions-key': FUNCTION_KEY };
  }
  return {};
};

/**
 * Converts a File object to a base64-encoded string.
 * Used when sending file content as JSON to the backend.
 */
async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Strip the data-URL prefix (e.g. "data:application/octet-stream;base64,")
      const base64 = result.includes(',') ? result.split(',')[1] : result;
      resolve(base64);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** Response from the Direct Line token endpoint. */
export interface DirectLineToken {
  conversationId: string;
  token: string;
  expires_in: number;
}

/**
 * Centralized API client.
 *
 * V2 methods (kept for backward compatibility):
 *   getDirectLineToken, postActivity, sendMessageToCopilot,
 *   getMessagesFromCopilot, trainModel, getModelHistory, setActiveModel,
 *   getModelInfo, getTrainingData, deleteTrainingData
 *
 * V3 additions:
 *   Sectors, Projects, submitClassificationJob, getJobStatus, getJobResults,
 *   reclassifyItems, approveClassifications, Knowledge Base CRUD
 */
export const apiClient = {

  // ==================== V2 METHODS (UNCHANGED) ====================

  /** Gets a temporary Direct Line token for Copilot chat communication. */
  async getDirectLineToken(): Promise<DirectLineToken> {
    const response = await axios.get(`${API_BASE_URL}/get-token`, {
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  async postActivity(conversationId: string, token: string, activity: unknown): Promise<unknown> {
    const response = await axios.post(
      `https://directline.botframework.com/v3/directline/conversations/${conversationId}/activities`,
      activity,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      }
    );
    return response.data;
  },

  async sendMessageToCopilot(
    conversationId: string,
    token: string,
    text: string,
    value?: unknown
  ): Promise<void> {
    const payload = {
      type: 'message',
      from: { id: 'user' },
      locale: 'pt-BR',
      text,
      value,
    };
    await axios.post(
      `https://directline.botframework.com/v3/directline/conversations/${conversationId}/activities`,
      payload,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      }
    );
  },

  async getMessagesFromCopilot(
    conversationId: string,
    token: string,
    watermark?: string
  ): Promise<unknown> {
    const url = watermark
      ? `https://directline.botframework.com/v3/directline/conversations/${conversationId}/activities?watermark=${watermark}`
      : `https://directline.botframework.com/v3/directline/conversations/${conversationId}/activities`;

    const response = await axios.get(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  async trainModel(fileContent: string, sector: string, filename: string): Promise<unknown> {
    const response = await axios.post(
      `${API_BASE_URL}/TrainModel`,
      { fileContent, sector, filename },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  async getModelHistory(sector: string): Promise<unknown[]> {
    console.log(`[API] Fetching model history for sector: ${sector}`);
    try {
      const response = await axios.get(`${API_BASE_URL}/GetModelHistory`, {
        params: { sector, t: Date.now() },
        headers: getAuthHeaders(),
      });
      console.log(`[API] Model history received: ${response.data?.length} entries`);
      return response.data;
    } catch (error) {
      console.error('[API] Error fetching model history:', error);
      throw error;
    }
  },

  async setActiveModel(sector: string, versionId: string): Promise<unknown> {
    const response = await axios.post(
      `${API_BASE_URL}/SetActiveModel`,
      { sector, version_id: versionId },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  async getModelInfo(sector: string, versionId?: string): Promise<unknown> {
    const response = await axios.get(`${API_BASE_URL}/GetModelInfo`, {
      params: { sector, version_id: versionId, t: Date.now() },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  async getTrainingData(
    sector: string,
    page: number = 1,
    pageSize: number = 50,
    filters?: { version?: string; n4?: string; search?: string }
  ): Promise<unknown> {
    const response = await axios.get(`${API_BASE_URL}/GetTrainingData`, {
      params: { sector, page, page_size: pageSize, ...filters },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  async deleteTrainingData(
    sector: string,
    options: {
      row_ids?: number[];
      version?: string;
      items?: { descricao: string; n4: string; version: string }[];
    }
  ): Promise<unknown> {
    const response = await axios.post(
      `${API_BASE_URL}/DeleteTrainingData`,
      { sector, ...options },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  // ==================== V3: SECTORS ====================

  /** Lists all available sectors. */
  async getSectors(): Promise<Sector[]> {
    const response = await axios.get(`${API_BASE_URL}/ListSectors`, {
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Creates a new sector. */
  async createSector(data: {
    name: string;
    display_name: string;
  }): Promise<Sector> {
    const response = await axios.post(`${API_BASE_URL}/CreateSector`, data, {
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  // ==================== V3: PROJECTS ====================

  /** Lists all projects. */
  async getProjects(): Promise<Project[]> {
    const response = await axios.get(`${API_BASE_URL}/ListProjects`, {
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Creates a new project. */
  async createProject(
    data: Partial<Project> & { display_name: string; sector: string }
  ): Promise<Project> {
    const response = await axios.post(`${API_BASE_URL}/CreateProject`, data, {
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Updates an existing project. */
  async updateProject(projectId: string, data: Partial<Project>): Promise<Project> {
    const response = await axios.put(
      `${API_BASE_URL}/UpdateProject`,
      { project_id: projectId, ...data },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  /** Deletes a project. */
  async deleteProject(projectId: string): Promise<void> {
    await axios.delete(`${API_BASE_URL}/DeleteProject`, {
      params: { projectId },
      headers: getAuthHeaders(),
    });
  },

  /** Deletes a sector. If force=true, also deletes all projects in the sector. */
  async deleteSector(
    sectorName: string,
    force: boolean = false
  ): Promise<{ success: boolean; deleted_sector: string; deleted_projects: string[] }> {
    const { data } = await axios.delete(`${API_BASE_URL}/DeleteSector`, {
      params: { sectorName, force: force.toString() },
      headers: getAuthHeaders(),
    });
    return data;
  },

  /** Returns the effective hierarchy for a project (own, inherited, or padrao). */
  async getProjectHierarchy(
    projectId: string
  ): Promise<{ hierarchy: HierarchyEntry[] | null; source: string }> {
    const response = await axios.get(`${API_BASE_URL}/GetProjectHierarchy`, {
      params: { projectId },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  // ==================== V3: CLASSIFICATION ====================

  /**
   * Submits a classification job (v3, project-aware).
   * Converts files to base64 and sends as JSON.
   * Returns the jobId immediately; use getJobStatus to poll.
   */
  async submitClassificationJob(params: {
    file: File;
    projectId?: string;
    sector?: string;
    descColumn?: string;
    hierarchyFile?: File;
  }): Promise<{ jobId: string }> {
    const fileContent = await fileToBase64(params.file);

    const requestBody: Record<string, unknown> = {
      fileContent,
      originalFilename: params.file.name,
    };

    if (params.projectId) requestBody.projectId = params.projectId;
    if (params.sector) requestBody.sector = params.sector;
    if (params.descColumn) requestBody.descColumn = params.descColumn;

    if (params.hierarchyFile) {
      requestBody.customHierarchy = await fileToBase64(params.hierarchyFile);
    }

    console.log('[API] Submitting classification job (v3)...');

    const response = await axios.post(`${API_BASE_URL}/SubmitTaxonomyJob`, requestBody, {
      headers: getAuthHeaders(),
    });

    const jobId: string = response.data.jobId;
    console.log(`[API] Job submitted. ID: ${jobId}`);
    return { jobId };
  },

  /**
   * Submits a classification job using pre-encoded base64 strings (v3).
   * Use this when the caller has already converted files to base64
   * (e.g. via FileReader in ClassifyTab). Returns jobId immediately.
   */
  async submitClassificationJobRaw(params: {
    fileContent: string;       // base64, no data-URL prefix
    originalFilename: string;
    projectId?: string;
    sector?: string;
    descColumn?: string;
    customHierarchy?: string;  // base64, no data-URL prefix
    clientContext?: string;
    useWebSearch?: boolean;
  }): Promise<{ jobId: string }> {
    const requestBody: Record<string, unknown> = {
      fileContent: params.fileContent,
      originalFilename: params.originalFilename,
    };

    if (params.projectId) requestBody.projectId = params.projectId;
    if (params.sector) requestBody.sector = params.sector;
    if (params.descColumn) requestBody.descColumn = params.descColumn;
    if (params.customHierarchy) requestBody.customHierarchy = params.customHierarchy;
    if (params.clientContext) requestBody.clientContext = params.clientContext;
    if (params.useWebSearch) requestBody.useWebSearch = true;

    console.log('[API] Submitting classification job (raw base64, v3)...');

    const response = await axios.post(`${API_BASE_URL}/SubmitTaxonomyJob`, requestBody, {
      headers: getAuthHeaders(),
    });

    const jobId: string = response.data.jobId;
    console.log(`[API] Job submitted. ID: ${jobId}`);
    return { jobId };
  },

  /** Polls the status of a classification job. */
  async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    const response = await axios.get(`${API_BASE_URL}/GetTaxonomyJobStatus`, {
      params: { jobId },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Cancels a PENDING or PROCESSING job. */
  async cancelJob(jobId: string): Promise<void> {
    await axios.post(`${API_BASE_URL}/CancelJob`, null, {
      params: { jobId },
      headers: getAuthHeaders(),
    });
  },

  /** Retrieves all classified items for a completed job, including analytics and summary. */
  async getJobResults(
    jobId: string
  ): Promise<{ jobId: string; status: string; items: ClassifiedItem[]; total: number; analytics?: any; summary?: any; extra_columns?: string[] }> {
    const response = await axios.get(`${API_BASE_URL}/GetJobResults`, {
      params: { jobId },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  // ==================== V3: REVIEW ====================

  /**
   * Re-classifies a subset of items using a consultant instruction (prompt).
   * Useful for bulk reclassification during the review step.
   */
  async reclassifyItems(params: {
    jobId: string;
    projectId: string;
    items: Array<{ index: number; description: string }>;
    instruction: string;
  }): Promise<{ results: ClassifiedItem[] }> {
    const response = await axios.post(`${API_BASE_URL}/ReclassifyItems`, params, {
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /**
   * Submits final review decisions for a job.
   * Items marked contribute_to_kb=true are added to the project KB.
   * Returns a download-ready Excel (base64) with approved classifications.
   */
  async approveClassifications(params: {
    jobId: string;
    projectId: string;
    decisions: Array<{
      index: number;
      description: string;
      decision: ReviewDecision;
      N1: string;
      N2: string;
      N3: string;
      N4: string;
      confidence: number;
      source: string;
      contribute_to_kb?: boolean;
      instruction_used?: string;
    }>;
  }): Promise<{
    success: boolean;
    kb_added: number;
    summary: ReviewSummary;
    download_filename?: string;
    file_content_base64?: string;
  }> {
    const response = await axios.post(`${API_BASE_URL}/ApproveClassifications`, params, {
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Downloads raw classification results as Excel (before review). */
  async downloadJobExcel(jobId: string): Promise<{ filename: string; file_content_base64: string }> {
    const response = await axios.get(`${API_BASE_URL}/DownloadJobExcel`, {
      params: { jobId },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  // ==================== V3: KNOWLEDGE BASE ====================

  /** Returns a paginated list of KB entries for a project. */
  async getKnowledgeBase(
    projectId: string,
    params?: {
      page?: number;
      pageSize?: number;
      source?: string;
      n4?: string;
      search?: string;
    }
  ): Promise<KBPage> {
    const response = await axios.get(`${API_BASE_URL}/GetKnowledgeBase`, {
      params: {
        projectId,
        page: params?.page ?? 1,
        pageSize: params?.pageSize ?? 50,
        source: params?.source,
        n4: params?.n4,
        search: params?.search,
      },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Adds a single entry to the project KB. */
  async addKBEntry(projectId: string, entry: Partial<KBEntry>): Promise<KBEntry> {
    const response = await axios.post(
      `${API_BASE_URL}/AddKBEntry`,
      { projectId, ...entry },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  /** Updates an existing KB entry. */
  async updateKBEntry(
    projectId: string,
    entryId: string,
    data: Partial<KBEntry>
  ): Promise<KBEntry> {
    const response = await axios.put(
      `${API_BASE_URL}/UpdateKBEntry`,
      { projectId, entryId, ...data },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  /** Deletes a KB entry by ID. */
  async deleteKBEntry(projectId: string, entryId: string): Promise<void> {
    await axios.delete(`${API_BASE_URL}/DeleteKBEntry`, {
      params: { projectId, entryId },
      headers: getAuthHeaders(),
    });
  },

  /** Returns KB coverage statistics for a project. */
  async getKBCoverage(projectId: string): Promise<KBCoverage> {
    const response = await axios.get(`${API_BASE_URL}/GetKBCoverage`, {
      params: { projectId },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Lists all KB snapshot versions for a project. */
  async getKBVersions(projectId: string): Promise<KBVersion[]> {
    const response = await axios.get(`${API_BASE_URL}/GetKBVersions`, {
      params: { projectId },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Rolls the KB back to a previous snapshot version. */
  async rollbackKB(projectId: string, versionId: string): Promise<void> {
    await axios.post(
      `${API_BASE_URL}/RollbackKB`,
      { projectId, versionId },
      { headers: getAuthHeaders() }
    );
  },

  /**
   * Exports the full KB for a project as a base64-encoded Excel file.
   * Convert to Blob on click using atob() + Uint8Array (do NOT use blob URLs).
   */
  async exportKB(projectId: string): Promise<string> {
    const response = await axios.get(`${API_BASE_URL}/ExportKB`, {
      params: { projectId },
      headers: getAuthHeaders(),
    });
    return response.data.file_content_base64 as string;
  },

  /**
   * Imports KB entries from a base64-encoded Excel file.
   * Returns the count of added entries and the new total.
   */
  async importKB(
    projectId: string,
    fileContentBase64: string
  ): Promise<{ added: number; total: number }> {
    const response = await axios.post(
      `${API_BASE_URL}/ImportKB`,
      { projectId, fileContentBase64 },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  // ==================== V3: SECTOR KNOWLEDGE BASE ====================

  /** Returns a paginated list of KB entries for a sector. */
  async getSectorKB(
    sectorName: string,
    params?: { page?: number; pageSize?: number; search?: string }
  ): Promise<KBPage> {
    const response = await axios.get(`${API_BASE_URL}/GetSectorKB`, {
      params: {
        sectorName,
        page: params?.page ?? 1,
        pageSize: params?.pageSize ?? 50,
        search: params?.search,
      },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Returns KB coverage for a sector against its hierarchy. */
  async getSectorKBCoverage(sectorName: string): Promise<KBCoverage> {
    const response = await axios.get(`${API_BASE_URL}/GetSectorKBCoverage`, {
      params: { sectorName },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Lists all KB snapshot versions for a sector. */
  async getSectorKBVersions(sectorName: string): Promise<KBVersion[]> {
    const response = await axios.get(`${API_BASE_URL}/GetSectorKBVersions`, {
      params: { sectorName },
      headers: getAuthHeaders(),
    });
    return response.data;
  },

  /** Exports sector KB as a base64-encoded Excel file. */
  async exportSectorKB(sectorName: string): Promise<string> {
    const response = await axios.get(`${API_BASE_URL}/ExportSectorKB`, {
      params: { sectorName },
      headers: getAuthHeaders(),
    });
    return response.data.file_content_base64 as string;
  },

  /** Imports KB entries into a sector from a base64-encoded Excel file. */
  async importSectorKB(
    sectorName: string,
    fileContentBase64: string
  ): Promise<{ added: number; total: number }> {
    const response = await axios.post(
      `${API_BASE_URL}/ImportSectorKB`,
      { sectorName, fileContentBase64 },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  /** Updates an existing sector KB entry. */
  async updateSectorKBEntry(
    sectorName: string,
    entryId: string,
    data: Partial<KBEntry>
  ): Promise<KBEntry> {
    const response = await axios.put(
      `${API_BASE_URL}/UpdateSectorKBEntry`,
      { sectorName, entryId, ...data },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  /** Deletes a sector KB entry by ID. */
  async deleteSectorKBEntry(sectorName: string, entryId: string): Promise<void> {
    await axios.delete(`${API_BASE_URL}/DeleteSectorKBEntry`, {
      params: { sectorName, entryId },
      headers: getAuthHeaders(),
    });
  },

  /** Rolls the sector KB back to a previous snapshot version. */
  async rollbackSectorKB(sectorName: string, versionId: string): Promise<void> {
    await axios.post(
      `${API_BASE_URL}/RollbackSectorKB`,
      { sectorName, versionId },
      { headers: getAuthHeaders() }
    );
  },

  /** Adds a single entry to the sector KB. */
  async addSectorKBEntry(sectorName: string, entry: Partial<KBEntry>): Promise<KBEntry> {
    const response = await axios.post(
      `${API_BASE_URL}/AddSectorKBEntry`,
      { sectorName, ...entry },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },

  /** Promotes selected entries from a project KB to the sector KB. */
  async promoteToSectorKB(
    projectId: string,
    sectorName: string,
    entryIds: string[]
  ): Promise<{ success: boolean; promoted_count: number }> {
    const response = await axios.post(
      `${API_BASE_URL}/PromoteToSectorKB`,
      { projectId, sectorName, entryIds },
      { headers: getAuthHeaders() }
    );
    return response.data;
  },
};
