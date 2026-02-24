import { useState, useEffect, useCallback } from 'react';
import type { Project, Sector } from '../lib/types';
import { saveProject, getAllProjectsLocal, deleteProjectLocal } from '../lib/database';

// Import api client lazily to avoid circular deps
const getApi = () => import('../lib/api').then(m => m.apiClient);

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = await getApi();
      const [projectsData, sectorsData] = await Promise.all([
        api.getProjects(),
        api.getSectors(),
      ]);
      setProjects(projectsData);
      setSectors(sectorsData);
      // Sync to IndexedDB
      for (const p of projectsData) {
        await saveProject(p);
      }
    } catch (e: any) {
      setError(e.message || 'Erro ao carregar projetos');
      // Fallback to local cache
      const local = await getAllProjectsLocal();
      setProjects(local);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const createProject = useCallback(async (data: {
    display_name: string;
    sector: string;
    client_context?: string;
    custom_hierarchy?: any[] | null;
    hierarchy_filename?: string | null;
  }) => {
    const api = await getApi();
    const project = await api.createProject(data);
    await saveProject(project);
    setProjects(prev => [...prev, project]);
    return project;
  }, []);

  const updateProject = useCallback(async (projectId: string, data: Partial<Project>) => {
    const api = await getApi();
    const updated = await api.updateProject(projectId, data);
    await saveProject(updated);
    setProjects(prev => prev.map(p => p.project_id === projectId ? updated : p));
    return updated;
  }, []);

  const deleteProject = useCallback(async (projectId: string) => {
    const api = await getApi();
    await api.deleteProject(projectId);
    await deleteProjectLocal(projectId);
    setProjects(prev => prev.filter(p => p.project_id !== projectId));
  }, []);

  const createSector = useCallback(async (data: { name: string; display_name: string; custom_hierarchy?: any[] | null }) => {
    const api = await getApi();
    const sector = await api.createSector(data);
    setSectors(prev => [...prev, sector]);
    return sector;
  }, []);

  // Group projects by sector for display
  const projectsBySector = projects.reduce<Record<string, Project[]>>((acc, p) => {
    if (!acc[p.sector]) acc[p.sector] = [];
    acc[p.sector].push(p);
    return acc;
  }, {});

  return {
    projects,
    sectors,
    projectsBySector,
    loading,
    error,
    fetchProjects,
    createProject,
    updateProject,
    deleteProject,
    createSector,
  };
}
