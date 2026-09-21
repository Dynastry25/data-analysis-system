"use client";

interface SkeletonProps {
  className?: string;
}

/** Shimmering placeholder used while tables and charts load. */
export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={`skeleton-shimmer rounded ${className}`}
    />
  );
}

export function TableSkeleton({ rows = 6, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading data">
      <Skeleton className="h-8 w-full" />
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-2">
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <Skeleton key={columnIndex} className="h-6 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton() {
  return (
    <div className="space-y-2" role="status" aria-label="Loading chart">
      <Skeleton className="h-[240px] w-full" />
      <div className="flex justify-center gap-2">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  );
}

export default Skeleton;
