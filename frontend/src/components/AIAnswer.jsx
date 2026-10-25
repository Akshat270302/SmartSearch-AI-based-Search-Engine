import { Sparkles } from "lucide-react";

function AIAnswer({ summary, sourceCount }) {
  const hasSummary = typeof summary === "string" && summary.trim().length > 0;

  return (
    <section
      className="w-full rounded-2xl border border-teal-400/20 bg-slate-900 p-5 text-left shadow-[0_20px_50px_-28px_rgba(20,184,166,0.3)] sm:p-8"
      aria-labelledby="ai-answer-heading"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2
          id="ai-answer-heading"
          className="flex items-center gap-2 text-base font-semibold tracking-tight text-white"
        >
          <Sparkles className="text-teal-400" size={18} aria-hidden="true" />
          AI Answer
        </h2>
        {typeof sourceCount === "number" && (
          <span className="text-xs text-slate-500">
            {sourceCount} {sourceCount === 1 ? "source" : "sources"} found
          </span>
        )}
      </div>
      {hasSummary ? (
        <p className="mt-5 whitespace-pre-line break-words text-[15px] leading-8 text-slate-300">
          {summary}
        </p>
      ) : (
        <p className="mt-5 text-sm leading-7 text-slate-400">
          No AI answer was returned for this question. Try searching again with
          a little more detail.
        </p>
      )}
    </section>
  );
}

export default AIAnswer;
