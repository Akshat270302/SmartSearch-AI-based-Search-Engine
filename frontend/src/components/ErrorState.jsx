import { RefreshCw } from "lucide-react";

function ErrorState({ message, onRetry, disabled = false }) {
  return (
    <div
      className="mt-8 w-full max-w-xl rounded-xl border border-rose-400/25 bg-rose-950/30 p-5 text-left"
      role="alert"
      aria-live="assertive"
    >
      <p className="text-sm leading-6 text-rose-200">
        {message || "Something went wrong while searching. Please try again."}
      </p>
      <button
        className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-lg border border-rose-400/30 bg-slate-900 px-3.5 py-2 text-sm font-medium text-rose-200 transition-colors duration-200 hover:border-rose-300/60 hover:bg-rose-950/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
        type="button"
        onClick={onRetry}
        disabled={disabled}
      >
        <RefreshCw size={16} aria-hidden="true" />
        Retry
      </button>
    </div>
  );
}

export default ErrorState;
