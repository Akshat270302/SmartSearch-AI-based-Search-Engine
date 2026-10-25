import { useState } from "react";

import SourceCard from "./SourceCard";

const INITIAL_RESULT_COUNT = 8;

function SearchResults({ results = [], totalResults }) {
  const [showAll, setShowAll] = useState(false);
  const visibleResults = showAll
    ? results
    : results.slice(0, INITIAL_RESULT_COUNT);
  const reportedTotal =
    typeof totalResults === "number" ? totalResults : results.length;
  const hasMoreResults = results.length > INITIAL_RESULT_COUNT;

  return (
    <section
      className="mt-10 w-full text-left"
      aria-labelledby="search-results-heading"
    >
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <h2
          id="search-results-heading"
          className="text-base font-semibold tracking-tight text-slate-200"
        >
          Sources
        </h2>
        <span className="text-xs text-slate-500">
          {reportedTotal} {reportedTotal === 1 ? "result" : "results"}
        </span>
      </div>

      {visibleResults.length > 0 ? (
        <div className="space-y-3">
          {visibleResults.map((result, index) => (
            <SourceCard
              key={`${result?.url || "source"}-${result?.title || "untitled"}-${index}`}
              source={result}
            />
          ))}
        </div>
      ) : (
        <p className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 text-sm text-slate-400">
          No web sources were returned for this search.
        </p>
      )}

      {hasMoreResults && (
        <button
          className="mt-5 min-h-10 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-300 transition-colors duration-200 hover:border-teal-400/70 hover:text-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          type="button"
          onClick={() => setShowAll((current) => !current)}
        >
          {showAll ? "Show less" : `Show more (${results.length - INITIAL_RESULT_COUNT})`}
        </button>
      )}
    </section>
  );
}

export default SearchResults;
