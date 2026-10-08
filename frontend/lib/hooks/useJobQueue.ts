"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { JobRecord, JobStatus, JobType, api } from "@/lib/api";

export type { JobRecord, JobStatus, JobType };

interface UseJobQueueOptions {
  jobType?: JobType;
  datasetId?: number;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

interface UseJobQueueReturn {
  jobs: JobRecord[];
  loading: boolean;
  error: string | null;
  createJob: (payload: { job_type: JobType; dataset_id?: number; payload?: Record<string, any> }) => Promise<JobRecord | null>;
  cancelJob: (jobId: number) => Promise<void>;
  refresh: () => Promise<void>;
  getJob: (jobId: number) => Promise<JobRecord | null>;
  subscribeToProgress: (jobId: number, onProgress: (progress: number, status: JobStatus) => void) => () => void;
}

export function useJobQueue(options: UseJobQueueOptions = {}): UseJobQueueReturn {
  const { jobType, datasetId, autoRefresh = false, refreshInterval = 3000 } = options;
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const progressCallbacksRef = useRef<Map<number, (progress: number, status: JobStatus) => void>>(new Map());
  const refreshTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, any> = {};
      if (jobType) params.job_type = jobType;
      if (datasetId) params.dataset_id = datasetId;
      params.page = 1;
      params.page_size = 50;

      const response = await (api as any).jobs.list(params);
      setJobs(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch jobs");
    } finally {
      setLoading(false);
    }
  }, [jobType, datasetId]);

  const createJob = useCallback(async (payload: { job_type: JobType; dataset_id?: number; payload?: Record<string, any> }) => {
    try {
      const job = await (api as any).jobs.create(payload);
      await fetchJobs();
      return job;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
      return null;
    }
  }, [fetchJobs]);

  const cancelJob = useCallback(async (jobId: number) => {
    try {
      await (api as any).jobs.cancel(jobId);
      await fetchJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel job");
    }
  }, [fetchJobs]);

  const getJob = useCallback(async (jobId: number) => {
    try {
      return await (api as any).jobs.get(jobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get job");
      return null;
    }
  }, []);

  const subscribeToProgress = useCallback((jobId: number, onProgress: (progress: number, status: JobStatus) => void) => {
    progressCallbacksRef.current.set(jobId, onProgress);

    // Connect WebSocket if not already connected
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/api/v1/jobs/ws`;
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "job_progress" && data.job_id) {
            const callback = progressCallbacksRef.current.get(data.job_id);
            if (callback) {
              callback(data.progress, data.status);
            }
          }
        } catch {
          // Ignore parsing errors
        }
      };

      wsRef.current.onerror = () => {
        // WebSocket error - will fall back to polling
      };

      wsRef.current.onclose = () => {
        // Reconnect after 5 seconds
        setTimeout(() => {
          if (progressCallbacksRef.current.size > 0) {
            subscribeToProgress(jobId, onProgress);
          }
        }, 5000);
      };
    }

    // Return unsubscribe function
    return () => {
      progressCallbacksRef.current.delete(jobId);
      if (progressCallbacksRef.current.size === 0 && wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // Auto-refresh for running jobs
  useEffect(() => {
    if (!autoRefresh) return;

    const checkRunningJobs = async () => {
      const runningJobs = jobs.filter((j) => j.status === "pending" || j.status === "running");
      if (runningJobs.length > 0) {
        await fetchJobs();
      }
    };

    refreshTimeoutRef.current = setInterval(checkRunningJobs, refreshInterval);
    return () => {
      if (refreshTimeoutRef.current) {
        clearInterval(refreshTimeoutRef.current);
      }
    };
  }, [autoRefresh, refreshInterval, jobs, fetchJobs]);

  // Initial fetch
  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (refreshTimeoutRef.current) {
        clearInterval(refreshTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    jobs,
    loading,
    error,
    createJob,
    cancelJob,
    refresh: fetchJobs,
    getJob,
    subscribeToProgress,
  };
}

export default useJobQueue;