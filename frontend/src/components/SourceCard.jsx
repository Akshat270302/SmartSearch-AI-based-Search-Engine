import { ExternalLink } from "lucide-react";

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

function SourceCard({ source }) {
  const safeUrl = getSafeUrl(source?.url);
  const title =
    typeof source?.title === "string" && source.title.trim()
      ? source.title.trim()
      : "Untitled source";
  const snippet =
    typeof source?.snippet === "string" && source.snippet.trim()
      ? source.snippet.trim()
      : "No description available.";
  const engine =
    typeof source?.engine === "string" && source.engine.trim()
      ? source.engine.trim()
      : "";

  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 transition-[border-color,background-color,transform] duration-200 hover:-translate-y-0.5 hover:border-slate-700 hover:bg-slate-900">
      {safeUrl ? (
        <a
          className="group inline-flex max-w-full items-start gap-2 text-base font-semibold leading-6 text-slate-100 transition-colors duration-200 hover:text-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          href={safeUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          <span className="break-words">{title}</span>
          <ExternalLink
            className="mt-0.5 shrink-0 text-slate-500 transition-colors group-hover:text-teal-400"
            size={16}
            aria-hidden="true"
          />
        </a>
      ) : (
        <p className="break-words text-base font-semibold leading-6 text-slate-100">
          {title}
        </p>
      )}
      <p className="mt-2 break-words text-sm leading-6 text-slate-400">{snippet}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        {engine ? <span>{engine}</span> : <span>Source</span>}
        {!safeUrl && <span>• Link unavailable</span>}
      </div>
    </article>
  );
}

export default SourceCard;
