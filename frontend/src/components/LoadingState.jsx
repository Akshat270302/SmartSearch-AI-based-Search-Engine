import { LoaderCircle } from "lucide-react";

function LoadingState() {
  return (
    <div className="mt-8 flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-400" role="status" aria-live="polite">
      <LoaderCircle className="animate-spin text-teal-400" size={18} aria-hidden="true" />
      <span>Searching the web and preparing your answer...</span>
    </div>
  );
}

export default LoadingState;
