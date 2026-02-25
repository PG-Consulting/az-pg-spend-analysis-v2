/**
 * @fileoverview Tests for the useProjects hook (Spend Analysis v3).
 *
 * The hook manages projects and sectors state, syncing with the backend API
 * and falling back to IndexedDB when the API is unreachable.
 *
 * We test the hook via @testing-library/react renderHook, mocking
 * IndexedDB persistence (saveProject, getAllProjectsLocal, deleteProjectLocal)
 * and the API client (lazy-imported via dynamic import).
 */

import { renderHook, act } from '@testing-library/react';
import { useProjects } from '../hooks/useProjects';
import type { Project, Sector } from '../lib/types';

// ---------------------------------------------------------------------------
// Mock IndexedDB persistence layer
// ---------------------------------------------------------------------------
jest.mock('../lib/database', () => ({
  saveProject: jest.fn().mockResolvedValue(undefined),
  getAllProjectsLocal: jest.fn().mockResolvedValue([]),
  deleteProjectLocal: jest.fn().mockResolvedValue(undefined),
}));

// ---------------------------------------------------------------------------
// Mock API module — getApi() lazy import
// The hook does: const getApi = () => import('../lib/api').then(m => m.apiClient)
// ---------------------------------------------------------------------------
jest.mock('../lib/api', () => ({
  apiClient: {
    getProjects: jest.fn().mockResolvedValue([]),
    getSectors: jest.fn().mockResolvedValue([]),
    createProject: jest.fn(),
    updateProject: jest.fn(),
    deleteProject: jest.fn().mockResolvedValue(undefined),
    createSector: jest.fn(),
    deleteSector: jest.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Import mocked modules for assertions
// ---------------------------------------------------------------------------
import { saveProject, getAllProjectsLocal, deleteProjectLocal } from '../lib/database';
import { apiClient } from '../lib/api';

// ---------------------------------------------------------------------------
// Test data factory
// ---------------------------------------------------------------------------
const mockProject: Project = {
  project_id: 'naval-test',
  display_name: 'Naval Test',
  sector: 'naval',
  client_context: '',
  custom_hierarchy: null,
  hierarchy_source: 'padrao',
  hierarchy_filename: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  few_shot_max_examples: 5,
  use_sector_kb: true,
};

const mockProject2: Project = {
  project_id: 'naval-wartsila',
  display_name: 'Naval Wartsila',
  sector: 'naval',
  client_context: 'Contexto do cliente',
  custom_hierarchy: null,
  hierarchy_source: 'padrao',
  hierarchy_filename: null,
  created_at: '2025-01-02T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
  few_shot_max_examples: 10,
  use_sector_kb: true,
};

const mockSector: Sector = {
  name: 'naval',
  display_name: 'Naval',
  created_at: '2025-01-01T00:00:00Z',
};

const mockSector2: Sector = {
  name: 'educacional',
  display_name: 'Educacional',
  created_at: '2025-01-02T00:00:00Z',
};

// ---------------------------------------------------------------------------
// Helper to flush async effects
// ---------------------------------------------------------------------------
const flush = async () => {
  await act(async () => {
    await new Promise(r => setTimeout(r, 10));
  });
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('useProjects', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Default: API returns empty arrays
    (apiClient.getProjects as jest.Mock).mockResolvedValue([]);
    (apiClient.getSectors as jest.Mock).mockResolvedValue([]);
  });

  // 1. fetchProjects loads data on mount
  it('should fetch projects and sectors on mount', async () => {
    (apiClient.getProjects as jest.Mock).mockResolvedValue([mockProject, mockProject2]);
    (apiClient.getSectors as jest.Mock).mockResolvedValue([mockSector]);

    const { result } = renderHook(() => useProjects());

    await flush();

    expect(apiClient.getProjects).toHaveBeenCalledTimes(1);
    expect(apiClient.getSectors).toHaveBeenCalledTimes(1);
    expect(result.current.projects).toEqual([mockProject, mockProject2]);
    expect(result.current.sectors).toEqual([mockSector]);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  // 2. fetchProjects saves each project to IndexedDB
  it('should save each fetched project to IndexedDB', async () => {
    (apiClient.getProjects as jest.Mock).mockResolvedValue([mockProject, mockProject2]);
    (apiClient.getSectors as jest.Mock).mockResolvedValue([mockSector]);

    renderHook(() => useProjects());

    await flush();

    expect(saveProject).toHaveBeenCalledTimes(2);
    expect(saveProject).toHaveBeenCalledWith(mockProject);
    expect(saveProject).toHaveBeenCalledWith(mockProject2);
  });

  // 3. Fallback to IndexedDB on API error
  it('should fall back to IndexedDB when API fails and set error state', async () => {
    const localProjects = [mockProject];
    (apiClient.getProjects as jest.Mock).mockRejectedValue(new Error('Network error'));
    (getAllProjectsLocal as jest.Mock).mockResolvedValue(localProjects);

    const { result } = renderHook(() => useProjects());

    await flush();

    expect(result.current.error).toBe('Network error');
    expect(result.current.projects).toEqual(localProjects);
    expect(getAllProjectsLocal).toHaveBeenCalledTimes(1);
    expect(result.current.loading).toBe(false);
  });

  // 4. createProject
  it('should create a project via API, save to IndexedDB, and add to state', async () => {
    const { result } = renderHook(() => useProjects());
    await flush();

    const newProject: Project = { ...mockProject, project_id: 'naval-novo', display_name: 'Naval Novo' };
    (apiClient.createProject as jest.Mock).mockResolvedValue(newProject);

    let returned: Project | undefined;
    await act(async () => {
      returned = await result.current.createProject({
        display_name: 'Naval Novo',
        sector: 'naval',
      });
    });

    expect(apiClient.createProject).toHaveBeenCalledWith({
      display_name: 'Naval Novo',
      sector: 'naval',
    });
    expect(saveProject).toHaveBeenCalledWith(newProject);
    expect(returned).toEqual(newProject);
    expect(result.current.projects).toContainEqual(newProject);
  });

  // 5. updateProject
  it('should update a project via API, save to IndexedDB, and replace in state', async () => {
    (apiClient.getProjects as jest.Mock).mockResolvedValue([mockProject]);
    (apiClient.getSectors as jest.Mock).mockResolvedValue([mockSector]);

    const { result } = renderHook(() => useProjects());
    await flush();

    expect(result.current.projects).toHaveLength(1);

    const updatedProject: Project = { ...mockProject, display_name: 'Naval Atualizado' };
    (apiClient.updateProject as jest.Mock).mockResolvedValue(updatedProject);

    let returned: Project | undefined;
    await act(async () => {
      returned = await result.current.updateProject('naval-test', { display_name: 'Naval Atualizado' });
    });

    expect(apiClient.updateProject).toHaveBeenCalledWith('naval-test', { display_name: 'Naval Atualizado' });
    expect(saveProject).toHaveBeenCalledWith(updatedProject);
    expect(returned).toEqual(updatedProject);
    expect(result.current.projects[0].display_name).toBe('Naval Atualizado');
  });

  // 6. deleteProject
  it('should delete a project via API, remove from IndexedDB, and remove from state', async () => {
    (apiClient.getProjects as jest.Mock).mockResolvedValue([mockProject, mockProject2]);
    (apiClient.getSectors as jest.Mock).mockResolvedValue([mockSector]);

    const { result } = renderHook(() => useProjects());
    await flush();

    expect(result.current.projects).toHaveLength(2);

    await act(async () => {
      await result.current.deleteProject('naval-test');
    });

    expect(apiClient.deleteProject).toHaveBeenCalledWith('naval-test');
    expect(deleteProjectLocal).toHaveBeenCalledWith('naval-test');
    expect(result.current.projects).toHaveLength(1);
    expect(result.current.projects[0].project_id).toBe('naval-wartsila');
  });

  // 7. createSector
  it('should create a sector via API and add to sectors state', async () => {
    const { result } = renderHook(() => useProjects());
    await flush();

    (apiClient.createSector as jest.Mock).mockResolvedValue(mockSector2);

    let returned: Sector | undefined;
    await act(async () => {
      returned = await result.current.createSector({ name: 'educacional', display_name: 'Educacional' });
    });

    expect(apiClient.createSector).toHaveBeenCalledWith({ name: 'educacional', display_name: 'Educacional' });
    expect(returned).toEqual(mockSector2);
    expect(result.current.sectors).toContainEqual(mockSector2);
  });

  // 8. deleteSector without force
  it('should delete a sector via API without force and remove from sectors state', async () => {
    (apiClient.getProjects as jest.Mock).mockResolvedValue([mockProject]);
    (apiClient.getSectors as jest.Mock).mockResolvedValue([mockSector, mockSector2]);
    (apiClient.deleteSector as jest.Mock).mockResolvedValue({
      success: true,
      deleted_sector: 'educacional',
      deleted_projects: [],
    });

    const { result } = renderHook(() => useProjects());
    await flush();

    expect(result.current.sectors).toHaveLength(2);

    await act(async () => {
      await result.current.deleteSector('educacional');
    });

    expect(apiClient.deleteSector).toHaveBeenCalledWith('educacional', false);
    expect(result.current.sectors).toHaveLength(1);
    expect(result.current.sectors[0].name).toBe('naval');
    // Projects remain unchanged
    expect(result.current.projects).toHaveLength(1);
    expect(deleteProjectLocal).not.toHaveBeenCalled();
  });

  // 9. deleteSector with force — removes sector AND its projects
  it('should delete a sector with force=true, removing sector and its projects from state', async () => {
    (apiClient.getProjects as jest.Mock).mockResolvedValue([mockProject, mockProject2]);
    (apiClient.getSectors as jest.Mock).mockResolvedValue([mockSector, mockSector2]);
    (apiClient.deleteSector as jest.Mock).mockResolvedValue({
      success: true,
      deleted_sector: 'naval',
      deleted_projects: ['naval-test', 'naval-wartsila'],
    });

    const { result } = renderHook(() => useProjects());
    await flush();

    expect(result.current.projects).toHaveLength(2);
    expect(result.current.sectors).toHaveLength(2);

    await act(async () => {
      await result.current.deleteSector('naval', true);
    });

    expect(apiClient.deleteSector).toHaveBeenCalledWith('naval', true);
    // Sector removed
    expect(result.current.sectors).toHaveLength(1);
    expect(result.current.sectors[0].name).toBe('educacional');
    // All projects in the deleted sector removed
    expect(result.current.projects).toHaveLength(0);
    // IndexedDB cleanup for each deleted project
    expect(deleteProjectLocal).toHaveBeenCalledWith('naval-test');
    expect(deleteProjectLocal).toHaveBeenCalledWith('naval-wartsila');
  });

  // 10. Error state is cleared on successful refetch
  it('should clear error state after a successful refetch', async () => {
    // First mount: API fails
    (apiClient.getProjects as jest.Mock).mockRejectedValue(new Error('Server down'));
    (getAllProjectsLocal as jest.Mock).mockResolvedValue([]);

    const { result } = renderHook(() => useProjects());
    await flush();

    expect(result.current.error).toBe('Server down');

    // Now API recovers
    (apiClient.getProjects as jest.Mock).mockResolvedValue([mockProject]);
    (apiClient.getSectors as jest.Mock).mockResolvedValue([mockSector]);

    await act(async () => {
      await result.current.fetchProjects();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.projects).toEqual([mockProject]);
    expect(result.current.sectors).toEqual([mockSector]);
  });
});
