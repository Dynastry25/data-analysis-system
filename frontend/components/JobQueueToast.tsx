"use client";

import { useEffect, useState } from "react";
import { JobRecord, JobStatus, useJobQueue } from "@/lib/hooks/useJobQueue";
import { useToast } from "@/components/Toast";

interface JobQueueToastOptions {
  jobType?: JobRecord["job_type"];
  datasetId?: number;
}

export function JobQueueToast({ jobType, datasetId }: JobQueueToastOptions = {}) {
  const { showToast } = useToast();
  const [notifiedJobs, setNotifiedJobs] = useState<Set<number>>(new Set());

  const { jobs } = useJobQueue({
    jobType,
    datasetId,
    autoRefresh: true,
    refreshInterval: 5000,
  });

  useEffect(() => {
    const completedJobs = jobs.filter(
      (job) => job.status === "completed" || job.status === "failed"
    );

    for (const job of completedJobs) {
      if (!notifiedJobs.has(job.id)) {
        if (job.status === "completed") {
          showToast(
            `${formatJobType(job.job_type)} completed successfully`,
            "success"
          );
        } else {
          showToast(
            `${formatJobType(job.job_type)} failed: ${job.error_message || "Unknown error"}`,
            "danger"
          );
        }
        setNotifiedJobs((prev) => new Set(prev).add(job.id));
      }
    }
  }, [jobs, notifiedJobs, showToast]);

  return null;
}

function formatJobType(type: JobRecord["job_type"]): string {
  const labels: Record<string, string> = {
    analysis: "Analysis",
    report_export: "Report export",
    dataset_clean: "Dataset cleaning",
    dataset_transform: "Dataset transformation",
    chart_render: "Chart rendering",
    ml_training: "ML training",
  };
  return labels[type] || type;
}

export default JobQueueToast;