import { useEffect, useRef, useState } from "react";

import AIAnswer from "./components/AIAnswer";
import ErrorState from "./components/ErrorState";
import Header from "./components/Header";
import LoadingState from "./components/LoadingState";
import SearchBar from "./components/SearchBar";
import SearchResults from "./components/SearchResults";
import { askQuestion } from "./services/api";

const PRODUCT_NAME = "SearchAI";

const EXAMPLE_QUERIES = [
  "What is machine learning?",
  "Latest developments in space exploration",
  "How does Docker work?",
];

function App() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [response, setResponse] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const abortControllerRef = useRef(null);
  const answerRef = useRef(null);

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    if (response) {
      answerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [response]);

  async function runSearch(searchQuery) {
    if (!searchQuery || isLoading) {
      return;
    }

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);
    setError("");
    setResponse(null);
    setSubmittedQuery(searchQuery);

    try {
      const result = await askQuestion(searchQuery, {
        signal: controller.signal,
      });
      setResponse(result);
    } catch (requestError) {
      if (requestError.name !== "AbortError") {
        setError(
          requestError instanceof Error && requestError.message
            ? requestError.message
            : "Something went wrong while searching. Please try again.",
        );
      }
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
        setIsLoading(false);
      }
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    const trimmedQuery = query.trim();

    if (!trimmedQuery || isLoading) {
      return;
    }

    runSearch(trimmedQuery);
  }

  function handleRetry() {
    if (submittedQuery) {
      runSearch(submittedQuery);
    }
  }

  function handleExampleClick(example) {
    if (isLoading) {
      return;
    }

    setQuery(example);
  }

  function handleClearQuery() {
    if (!isLoading) {
      setQuery("");
    }
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-slate-950 text-slate-100">
      <Header productName={PRODUCT_NAME} />
      <section
        id="about"
        className="mx-auto flex min-h-[calc(100vh-73px)] w-full max-w-6xl flex-col items-center justify-center px-4 pb-20 pt-14 text-center sm:px-8 sm:pt-20"
      >
        <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-400 shadow-sm">
          <span className="h-1.5 w-1.5 rounded-full bg-teal-400" />
          Search, clarified
        </div>
        <h1 className="max-w-3xl text-4xl font-semibold tracking-[-0.045em] text-white sm:text-6xl lg:text-7xl">
          Search the web smarter.
        </h1>
        <p className="mt-6 max-w-xl text-base leading-7 text-slate-400 sm:text-lg">
          AI-powered answers backed by real web sources.
        </p>

        <div className="mt-10 w-full max-w-3xl">
          <SearchBar
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onSubmit={handleSubmit}
            disabled={isLoading}
            onClear={handleClearQuery}
          />
          <div className="mt-5 flex flex-wrap justify-center gap-2.5" aria-label="Example queries">
            {EXAMPLE_QUERIES.map((example) => (
              <button
                className="min-h-10 rounded-full border border-slate-800 bg-slate-900 px-3.5 py-2 text-left text-xs text-slate-400 transition-colors duration-200 hover:border-teal-500/60 hover:text-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 sm:text-sm"
                key={example}
                type="button"
                onClick={() => handleExampleClick(example)}
                disabled={isLoading}
              >
                {example}
              </button>
            ))}
          </div>
        </div>

        {isLoading && <LoadingState />}

        {error && (
          <ErrorState
            message={error}
            onRetry={handleRetry}
            disabled={isLoading || !submittedQuery}
          />
        )}

        {response && !isLoading && (
          <div
            className="mt-10 w-full max-w-2xl scroll-mt-6"
            ref={answerRef}
            aria-live="polite"
          >
            <AIAnswer
              summary={response.summary}
              sourceCount={response.results.length}
            />
            <SearchResults
              results={response.results}
              totalResults={response.total_results}
            />
          </div>
        )}

        {!response && !error && !isLoading && (
          <p className="mt-16 text-xs text-slate-400">
            Explore ideas, understand topics, and find what matters.
          </p>
        )}
      </section>
    </main>
  );
}

export default App;
