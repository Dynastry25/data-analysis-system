"use client";

import { useEffect, useState } from "react";
import { JobRecord, JobStatus, JobType, useJobQueue } from "@/lib/hooks/useJobQueue";
import { useToast } from "@/components/Toast";

const STATUS_COLORS: Record<JobStatus, string> = {
  pending: "bg-gray-500",
  running: "bg-blue-500",
  completed: "bg-green-500",
  failed: "bg-red-500",
  cancelled: "bg-orange-500",
};

const STATUS_LABELS: Record<JobStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

const TYPE_LABELS: Record<JobType, string> = {
  analysis: "Analysis",
  report_export: "Report Export",
  chart_render: "Chart Render",
  ml_training: "ML Training",
  dataset_clean: "Dataset Clean",
  dataset_transform: "Dataset Transform",
};

interface JobQueuePanelProps {
  jobType?: JobType;
  datasetId?: number;
  autoRefresh?: boolean;
}

export function JobQueuePanel({ jobType, datasetId, autoRefresh = true }: JobQueuePanelProps) {
  const { showToast } = useToast();
  const { jobs, loading, error, cancelJob, refresh, subscribeToProgress, getJob } = useJobQueue({
    jobType,
    datasetId,
    autoRefresh,
    refreshInterval: 3000,
  });

  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [progressMap, setProgressMap] = useState<Record<number, { progress: number; status: JobStatus }>>({});

  // Subscribe to progress for running jobs
  useEffect(() => {
    const runningJobs = jobs.filter((j) => j.status === "pending" || j.status === "running");
    const unsubscribes: (() => void)[] = [];

    for (const job of runningJobs) {
      const unsubscribe = subscribeToProgress(job.id, (progress, status) => {
        setProgressMap((prev) => ({
          ...prev,
          [job.id]: { progress, status },
        }));
      });
      unsubscribes.push(unsubscribe);
    }

    return () => {
      unsubscribes.forEach((fn) => fn());
    };
  }, [jobs, subscribeToProgress]);

  const handleCancel = async (jobId: number) => {
    if (confirm("Are you sure you want to cancel this job?")) {
      await cancelJob(jobId);
      showToast("Job cancelled", "info");
    }
  };

  const handleStart = async (jobId: number) => {
    try {
      const job = await getJob(jobId);
      if (job) {
        showToast("Job started", "success");
        refresh();
      }
    } catch {
      showToast("Failed to start job", "danger");
    }
  };

  const handleViewResult = async (jobId: number) => {
    const job = await getJob(jobId);
    if (job?.result) {
      alert(JSON.stringify(job.result, null, 2));
    }
  };

  const getProgress = (job: JobRecord) => {
    const live = progressMap[job.id];
    if (live) return live.progress;
    return job.progress;
  };

  const getStatus = (job: JobRecord): JobStatus => {
    const live = progressMap[job.id];
    if (live) return live.status;
    return job.status;
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500">
        Loading jobs...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center text-red-500">
        Error: {error}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Job Queue</h3>
        <button
          onClick={refresh}
          disabled={loading}
          className="px-3 py-1 text-sm bg-gray-100 hover:bg-gray-200 rounded transition"
        >
          Refresh
        </button>
      </div>

      {jobs.length === 0 ? (
        <div className="p-8 text-center text-gray-500">
          No jobs found.{" "}
          {jobType && <span> for {TYPE_LABELS[jobType]}</span>}
          {datasetId && <span> on dataset {datasetId}</span>}
        </div>
      ) : (
        <div className="space-y-2">
          {jobs.map((job) => {
            const status = getStatus(job);
            const progress = getProgress(job);
            const isRunning = status === "running" || status === "pending";
            const isComplete = status === "completed" || status === "failed" || status === "cancelled";
            const isExpanded = expandedJobId === job.id;

            return (
              <div
                key={job.id}
                className="border rounded-lg p-4 bg-white shadow-sm hover:shadow-md transition"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-medium text-gray-900">
                        {TYPE_LABELS[job.job_type] || job.job_type}
                      </span>
                      <span
                        className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                          STATUS_COLORS[status]
                        } text-white`}
                      >
                        {STATUS_LABELS[status]}
                      </span>
                      {job.dataset_id && (
                        <span className="text-xs text-gray-500">
                          Dataset #{job.dataset_id}
                        </span>
                      )}
                    </div>

                    {isRunning && (
                      <div className="mt-2 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all duration-300 ${
                            status === "running" ? "bg-blue-500" : "bg-gray-400"
                          }`}
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    )}

                    {isComplete && job.error_message && (
                      <div className="mt-2 text-sm text-red-600">
                        Error: {job.error_message}
                      </div>
                    )}

                    {isComplete && job.result && !job.error_message && (
                      <button
                        onClick={() => handleViewResult(job.id)}
                        className="mt-2 text-sm text-blue-600 hover:underline"
                      >
                        View Result
                      </button>
                    )}

                    <div className="mt-2 text-xs text-gray-500 flex items-center gap-4">
                      <span>
                        Created: {job.created_at ? new Date(job.created_at).toLocaleString() : "N/A"}
                      </span>
                      {job.started_at && (
                        <span>Started: {new Date(job.started_at).toLocaleString()}</span>
                      )}
                      {job.completed_at && (
                        <span>Completed: {new Date(job.completed_at).toLocaleString()}</span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    {status === "pending" && (
                      <button
                        onClick={() => handleStart(job.id)}
                        className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 transition"
                      >
                        Start
                      </button>
                    )}

                    {isRunning && (
                      <button
                        onClick={() => handleCancel(job.id)}
                        className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 transition"
                      >
                        Cancel
                      </button>
                    )}

                    <button
                      onClick={() =>
                        setExpandedJobId(isExpanded ? null : job.id)
                      }
                      className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition"
                    >
                      {isExpanded ? "Hide" : "Details"}
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-4 p-3 bg-gray-50 rounded border border-gray-200">
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="font-medium text-gray-500">Job ID:</span>{" "}
                        <span className="text-gray-900">{job.id}</span>
                      </div>
                      <div>
                        <span className="font-medium text-gray-500">User:</span>{" "}
                        <span className="text-gray-900">
                          {job.user_email || job.user_id}
                        </span>
                      </div>
                      {job.organization_name && (
                        <div>
                          <span className="font-medium text-gray-500">Organization:</span>{" "}
                          <span className="text-gray-900">{job.organization_name}</span>
                        </div>
                      )}
                      <div>
                        <span className="font-medium text-gray-500">Type:</span>{" "}
                        <span className="text-gray-900">{job.job_type}</span>
                      </div>
                    </div>

                    <div className="mt-3">
                      <span className="font-medium text-gray-500">Payload:</span>
                      <pre className="mt-1 text-xs bg-gray-900 text-green-300 p-2 rounded overflow-auto max-h-48">
                        {JSON.stringify(job.payload, null, 2)}
                      </pre>
                    </div>

                    {job.result && (
                      <div className="mt-3">
                        <span className="font-medium text-gray-500">Result:</span>
                        <pre className="mt-1 text-xs bg-gray-900 text-green-300 p-2 rounded overflow-auto max-h-48">
                          {JSON.stringify(job.result, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default JobQueuePanel;