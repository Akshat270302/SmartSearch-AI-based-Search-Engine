import { ExternalLink, Image as ImageIcon } from "lucide-react";

function getSafeUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;

  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function ImageResults({ results = [], totalResults }) {
  const imageResults = results.filter((result) => getSafeUrl(result?.thumbnail_url || result?.image_url));

  return (
    <section className="mt-10 w-full text-left" aria-labelledby="image-results-heading">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="image-results-heading" className="flex items-center gap-2 text-base font-semibold text-slate-200">
          <ImageIcon size={17} className="text-teal-400" aria-hidden="true" />
          Images
        </h2>
        <span className="text-xs text-slate-500">
          {typeof totalResults === "number" ? totalResults : imageResults.length} results
        </span>
      </div>

      {imageResults.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {imageResults.map((result, index) => {
            const imageUrl = getSafeUrl(result.thumbnail_url || result.image_url);
            const sourceUrl = getSafeUrl(result.url);
            const title = result.title?.trim() || "Untitled image";

            return (
              <article className="group min-w-0 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70" key={`${imageUrl}-${index}`}>
                <a
                  className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-400"
                  href={sourceUrl || imageUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Open image source: ${title}`}
                >
                  <img
                    className="aspect-square w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    src={imageUrl}
                    alt={title}
                    loading="lazy"
                  />
                </a>
                <div className="p-3">
                  <p className="line-clamp-2 break-words text-sm text-slate-300">{title}</p>
                  {sourceUrl && (
                    <a
                      className="mt-2 inline-flex items-center gap-1 text-xs text-teal-300 hover:text-teal-200"
                      href={sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open source <ExternalLink size={12} aria-hidden="true" />
                    </a>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 text-sm text-slate-400">
          No image thumbnails were returned for this search.
        </p>
      )}
    </section>
  );
}

export default ImageResults;
