// Central type definitions for Spend.AI v3

// ==================== PROJECTS ====================

export interface Sector {
  name: string;           // lowercase, folder name
  display_name: string;
  created_at: string;
}

export interface Project {
  project_id: string;
  display_name: string;
  sector: string;
  client_context: string;
  custom_hierarchy: HierarchyEntry[] | null;
  hierarchy_source: 'own' | 'padrao';
  hierarchy_filename: string | null;
  created_at: string;
  updated_at: string;
  few_shot_max_examples: number;
  use_sector_kb?: boolean;
}

export interface HierarchyEntry {
  N1: string;
  N2: string;
  N3: string;
  N4: string;
}

export interface HierarchyTree {
  [n1: string]: {
    [n2: string]: {
      [n3: string]: string[]; // N4 values
    };
  };
}

// ==================== CLASSIFICATION ====================

export interface ClassifiedItem {
  index: number;
  description: string;
  N1: string;
  N2: string;
  N3: string;
  N4: string;
  confidence: number;
  source: string;
  status: string; // "Único" | "Ambíguo" | "Nenhum"
  // Optional original values (before correction)
  originalN1?: string;
  originalN2?: string;
  originalN3?: string;
  originalN4?: string;
  validatorAction?: string;
}

// ==================== REVIEW ====================

export type ReviewDecision = 'approved' | 'edited' | 'rejected' | 'pending';
export type ReviewFilter = 'all' | 'needs_attention' | 'low_confidence' | 'corrected' | 'approved' | 'rejected' | 'pending';
export type ReviewState = 'pending' | 'in_progress' | 'completed';

export interface ReviewItemState {
  decision: ReviewDecision;
  editedN1?: string;
  editedN2?: string;
  editedN3?: string;
  editedN4?: string;
  contributeToKB?: boolean;
  instructionUsed?: string;
}

export interface ReviewSummary {
  total: number;
  approved: number;
  edited: number;
  rejected: number;
  kb_added: number;
}

// ==================== SESSION ====================

export interface TaxonomySession {
  sessionId: string;
  projectId?: string;
  filename: string;
  sector?: string;
  timestamp: number;
  jobId?: string;
  /** Background job status for v3 async classification */
  jobStatus?: 'PENDING' | 'PROCESSING' | 'CLASSIFIED' | 'ERROR';
  summary?: Record<string, unknown>;
  analytics?: Record<string, unknown>;
  items?: ClassifiedItem[];
  downloadFilename?: string;
  fileContentBase64?: string;
  // Review state
  reviewState: ReviewState;
  reviewedCount: number;
  totalItems: number;
  reviewSummary?: ReviewSummary;
  approvedFileContentBase64?: string;
  approvedDownloadFilename?: string;
  extraColumns?: string[];
}

// ==================== KNOWLEDGE BASE ====================

export type KBSource = 'llm_approved' | 'consultant_correction' | 'reclassified_with_guidance';

export interface KBEntry {
  id: string;
  description: string;
  description_norm: string;
  N1: string;
  N2: string;
  N3: string;
  N4: string;
  source: KBSource;
  confidence: number;
  instruction_used: string | null;
  version: string;
  date_added: string;
  /** UI-only field: indicates whether entry comes from project, sector, or both KBs */
  _origin?: 'project' | 'sector' | 'both';
}

export interface KBPage {
  entries: KBEntry[];
  total: number;
  page: number;
  pages: number;
}

export interface KBCoverage {
  total_n4s: number;
  covered: number;
  pct: number;
  underserved: string[];
  /** Breakdown counts from merged KB */
  project_entries?: number;
  sector_entries?: number;
  merged_entries?: number;
}

export interface KBVersion {
  version_id: string;
  created_at: string;
  entry_count: number;
}

// ==================== JOB STATUS ====================

export type JobStatus = 'PENDING' | 'PROCESSING' | 'CLASSIFIED' | 'COMPLETED' | 'ERROR' | 'CANCELLED';

export interface JobStatusResponse {
  jobId: string;
  status: JobStatus;
  progress?: number;
  total_chunks?: number;
  processed_chunks?: number;
  error?: string;
  summary?: Record<string, unknown>;
  analytics?: Record<string, unknown>;
  download_filename?: string;
  file_content_base64?: string;
  // Review-related
  review_summary?: ReviewSummary;
  approved_file_content_base64?: string;
  approved_download_filename?: string;
}
