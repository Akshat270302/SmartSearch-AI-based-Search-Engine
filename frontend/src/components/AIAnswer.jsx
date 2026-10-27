import { ExternalLink, Sparkles } from "lucide-react";

function getSafeUrl(value) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }

  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function getSourceDetails(source) {
  const url = getSafeUrl(source?.url);
  let domain =
    typeof source?.domain === "string" && source.domain.trim()
      ? source.domain.trim()
      : "";

  if (!domain && url) {
    domain = new URL(url).hostname;
  }

  return {
    id: typeof source?.source_id === "string" ? source.source_id : "",
    url,
    title:
      typeof source?.title === "string" && source.title.trim()
        ? source.title.trim()
        : "Untitled source",
    domain: domain || "Unknown domain",
    date:
      typeof source?.published_date === "string" && source.published_date.trim()
        ? source.published_date.trim()
        : "",
  };
}

function renderInlineContent(text, sourceMap) {
  const parts = text.split(/(\[source_\d+\])/g);

  return parts.map((part, index) => {
    const match = part.match(/^\[(source_\d+)\]$/);
    const source = match ? sourceMap.get(match[1]) : null;

    if (!source) {
      return <span key={`${part}-${index}`}>{part}</span>;
    }

    if (!source.url) {
      return (
        <span
          className="mx-0.5 rounded bg-slate-800 px-1.5 py-0.5 text-xs font-semibold text-slate-400"
          key={`${part}-${index}`}
          title="Source link unavailable"
        >
          [{source.marker}]
        </span>
      );
    }

    return (
      <a
        className="mx-0.5 inline-flex rounded-md bg-teal-400/15 px-1.5 py-0.5 align-baseline text-xs font-semibold text-teal-300 transition-colors hover:bg-teal-400/25 hover:text-teal-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
        href={source.url}
        key={`${part}-${index}`}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Open cited source: ${source.title}`}
      >
        [{source.marker}]
      </a>
    );
  });
}

function AnswerContent({ summary, sourceMap }) {
  const lines = summary.split(/\r?\n/);
  const blocks = [];
  let currentParagraph = [];

  function flushParagraph() {
    if (currentParagraph.length > 0) {
      blocks.push({
        type: "paragraph",
        content: currentParagraph.join(" "),
      });
      currentParagraph = [];
    }
  }

  lines.forEach((line) => {
    const trimmedLine = line.trim();

    if (!trimmedLine) {
      flushParagraph();
      return;
    }

    const heading = trimmedLine.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      flushParagraph();
      blocks.push({ type: "heading", content: heading[1] });
      return;
    }

    const bullet = trimmedLine.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      blocks.push({ type: "bullet", content: bullet[1] });
      return;
    }

    currentParagraph.push(trimmedLine);
  });

  flushParagraph();

  return (
    <div className="mt-5 break-words text-[15px] leading-8 text-slate-300">
      {blocks.map((block, index) => {
        const content = renderInlineContent(block.content, sourceMap);

        if (block.type === "heading") {
          return (
            <h3 className="mt-5 text-base font-semibold text-slate-100 first:mt-0" key={index}>
              {content}
            </h3>
          );
        }

        if (block.type === "bullet") {
          return (
            <div className="flex gap-3" key={index}>
              <span className="mt-3 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-400" />
              <p>{content}</p>
            </div>
          );
        }

        return <p className={index > 0 ? "mt-4" : ""} key={index}>{content}</p>;
      })}
    </div>
  );
}

function CitedSources({ sources }) {
  if (sources.length === 0) {
    return null;
  }

  return (
    <div className="mt-7 border-t border-slate-800 pt-5">
      <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
        Cited sources
      </h3>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {sources.map((source, index) => (
          <div
            className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/50 p-3"
            key={source.id || `${source.url || "source"}-${index}`}
          >
            <div className="flex items-start gap-2">
              <span className="shrink-0 rounded bg-teal-400/15 px-1.5 py-0.5 text-xs font-semibold text-teal-300">
                [{index + 1}]
              </span>
              <div className="min-w-0">
                {source.url ? (
                  <a
                    className="inline-flex max-w-full items-center gap-1 text-sm font-medium text-slate-200 hover:text-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <span className="break-words">{source.title}</span>
                    <ExternalLink className="shrink-0" size={14} aria-hidden="true" />
                  </a>
                ) : (
                  <span className="break-words text-sm font-medium text-slate-300">
                    {source.title}
                  </span>
                )}
                <p className="mt-1 break-words text-xs text-slate-500">
                  {source.domain}
                  {source.date && ` · ${source.date}`}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AIAnswer({ summary, sourceCount, citations = [] }) {
  const hasSummary = typeof summary === "string" && summary.trim().length > 0;
  const sourceMap = new Map();
  const citationSources = [];
  const seenUrls = new Set();

  citations.forEach((citation) => {
    const source = getSourceDetails(citation);
    if (
      !source.id ||
      sourceMap.has(source.id) ||
      (source.url && seenUrls.has(source.url))
    ) {
      return;
    }

    if (source.url) {
      seenUrls.add(source.url);
    }
    source.marker = citationSources.length + 1;
    sourceMap.set(source.id, source);
    citationSources.push(source);
  });

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
        <AnswerContent summary={summary} sourceMap={sourceMap} />
      ) : (
        <p className="mt-5 text-sm leading-7 text-slate-400">
          No AI answer was returned for this question. Try searching again with
          a little more detail.
        </p>
      )}
      <CitedSources sources={citationSources} />
    </section>
  );
}

export default AIAnswer;
