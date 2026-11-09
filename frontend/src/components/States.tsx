interface ErrorStateProps {
  message?: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="panel mx-auto mt-16 max-w-md p-6 text-center">
      <h2 className="font-display text-2xl font-semibold">Could not load the dashboard</h2>
      <p className="mt-2 text-sm text-muted">
        {message ?? "The API did not respond. Check that the backend is running."}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-5 rounded-lg border border-champagne/60 bg-champagne/10 px-4 py-2 text-sm font-medium text-champagne hover:bg-champagne/20"
      >
        Retry
      </button>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Loading dashboard" className="space-y-5">
      <div className="skeleton h-16 w-full" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
        {Array.from({ length: 8 }, (_, index) => (
          <div key={index} className="skeleton h-28 w-full" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[55fr_45fr]">
        <div className="skeleton h-[440px] w-full" />
        <div className="skeleton h-[440px] w-full" />
      </div>
      <div className="skeleton h-56 w-full" />
    </div>
  );
}
