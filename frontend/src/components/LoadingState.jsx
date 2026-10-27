import { LoaderCircle } from "lucide-react";

function LoadingState({ onCancel, message = "Searching the web and preparing your answer..." }) {
  return (
    <div className="mt-8 flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-400" role="status" aria-live="polite">
      <LoaderCircle className="animate-spin text-teal-400" size={18} aria-hidden="true" />
      <span>{message}</span>
      {onCancel && (
        <button
          className="ml-auto min-h-9 rounded-lg border border-slate-700 px-3 py-1 text-xs font-medium text-slate-300 transition-colors hover:border-teal-400/70 hover:text-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
          type="button"
          onClick={onCancel}
        >
          Cancel
        </button>
      )}
    </div>
  );
}

export default LoadingState;
