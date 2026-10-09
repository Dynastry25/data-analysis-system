"use client";

import { JobQueuePanel } from "@/components/JobQueuePanel";

export default function JobsPage() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Job Queue</h1>
        <p className="text-gray-500 mt-1">
          Monitor and manage background jobs for long-running operations.
        </p>
      </div>
      <JobQueuePanel autoRefresh={true} />
    </div>
  );
}