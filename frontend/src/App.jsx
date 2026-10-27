import { useEffect, useRef, useState } from "react";

import AIAnswer from "./components/AIAnswer";
import ConversationView from "./components/ConversationView";
import ErrorState from "./components/ErrorState";
import Header from "./components/Header";
import ImageResults from "./components/ImageResults";
import LoadingState from "./components/LoadingState";
import SearchBar from "./components/SearchBar";
import SearchModeNav from "./components/SearchModeNav";
import SearchResults from "./components/SearchResults";
import { searchQuestion, streamQuestion } from "./services/api";

const PRODUCT_NAME = "SearchAI";
const MAX_CONVERSATION_MESSAGE_LENGTH = 4000;
const EXAMPLE_QUERIES = [
  "What is machine learning?",
  "Latest developments in space exploration",
  "How does Docker work?",
];

function createSession(query) {
  return {
    id: createId(),
    query,
    web: { results: null, totalResults: 0, status: "idle", error: "" },
    images: { results: null, totalResults: 0, status: "idle", error: "" },
    ai: {
      summary: "",
      citations: [],
      streamingAnswer: "",
      status: "idle",
      error: "",
    },
  };
}

function createId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function createConversation(sessionId) {
  return {
    id: createId(),
    sessionId,
    messages: [],
  };
}

function createMessage(role, content, extra = {}) {
  return {
    id: createId(),
    role,
    content,
    citations: [],
    status: "complete",
    ...extra,
  };
}

function getRequestError(error) {
  return error instanceof Error && error.message
    ? error.message
    : "Something went wrong while searching. Please try again.";
}

function App() {
  const [query, setQuery] = useState("");
  const [session, setSession] = useState(null);
  const [conversation, setConversation] = useState(null);
  const [mode, setMode] = useState("all");
  const sessionRef = useRef(null);
  const conversationRef = useRef(null);
  const requestsRef = useRef({ web: null, images: null, ai: null, conversation: null });
  const answerRef = useRef(null);

  function commitSession(nextSession) {
    sessionRef.current = nextSession;
    setSession(nextSession);
  }

  function commitConversation(nextConversation) {
    conversationRef.current = nextConversation;
    setConversation(nextConversation);
  }

  function updateSession(queryKey, sessionId, update) {
    const current = sessionRef.current;
    if (!current || current.query !== queryKey || current.id !== sessionId) return;
    const nextSession = update(current);
    commitSession(nextSession);
  }

  function updateConversation(sessionId, conversationId, update) {
    const current = conversationRef.current;
    if (
      !current ||
      current.sessionId !== sessionId ||
      current.id !== conversationId
    ) return;
    commitConversation(update(current));
  }

  function cancelRequest(type) {
    requestsRef.current[type]?.controller.abort();
    requestsRef.current[type] = null;
  }

  function cancelAllRequests() {
    ["web", "images", "ai", "conversation"].forEach(cancelRequest);
  }

  useEffect(() => {
    return () => cancelAllRequests();
  }, []);

  useEffect(() => {
    if (session?.ai.status === "complete" || session?.web.status === "complete") {
      answerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [session?.ai.status, session?.web.status]);

  useEffect(() => {
    if (!session || session.ai.status !== "complete") return;
    const current = conversationRef.current;
    if (
      !current ||
      current.sessionId !== session.id ||
      current.messages.length > 0
    ) return;

    commitConversation({
      ...current,
      messages: [
        createMessage("user", session.query),
        createMessage("assistant", session.ai.summary, {
          citations: session.ai.citations,
          sourceCount: session.web.results?.length,
        }),
      ],
    });
  }, [session]);

  async function loadWebResults(queryKey) {
    const current = sessionRef.current;
    if (!current || current.query !== queryKey) return;
    const sessionId = current.id;
    if (current.web.status === "complete") return current.web.results;
    if (requestsRef.current.web) return requestsRef.current.web.promise;

    const controller = new AbortController();
    updateSession(queryKey, sessionId, (value) => ({
      ...value,
      web: { ...value.web, status: "loading", error: "" },
    }));

    const promise = searchQuestion(queryKey, { signal: controller.signal })
      .then((payload) => {
        updateSession(queryKey, sessionId, (value) => ({
          ...value,
          web: {
            results: payload.results,
            totalResults: payload.total_results,
            status: "complete",
            error: "",
          },
        }));
        return payload.results;
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          updateSession(queryKey, sessionId, (value) => ({
            ...value,
            web: { ...value.web, status: "error", error: getRequestError(error) },
          }));
        }
        throw error;
      })
      .finally(() => {
        if (requestsRef.current.web?.controller === controller) {
          requestsRef.current.web = null;
        }
      });

    requestsRef.current.web = { controller, promise };
    return promise;
  }

  async function loadImageResults(queryKey) {
    const current = sessionRef.current;
    if (!current || current.query !== queryKey) return;
    const sessionId = current.id;
    if (current.images.status === "complete") return current.images.results;
    if (requestsRef.current.images) return requestsRef.current.images.promise;

    const controller = new AbortController();
    updateSession(queryKey, sessionId, (value) => ({
      ...value,
      images: { ...value.images, status: "loading", error: "" },
    }));

    const promise = searchQuestion(queryKey, {
      signal: controller.signal,
      category: "images",
    })
      .then((payload) => {
        updateSession(queryKey, sessionId, (value) => ({
          ...value,
          images: {
            results: payload.results,
            totalResults: payload.total_results,
            status: "complete",
            error: "",
          },
        }));
        return payload.results;
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          updateSession(queryKey, sessionId, (value) => ({
            ...value,
            images: {
              ...value.images,
              status: "error",
              error: getRequestError(error),
            },
          }));
        }
        throw error;
      })
      .finally(() => {
        if (requestsRef.current.images?.controller === controller) {
          requestsRef.current.images = null;
        }
      });

    requestsRef.current.images = { controller, promise };
    return promise;
  }

  async function loadAIAnswer(queryKey) {
    const current = sessionRef.current;
    if (!current || current.query !== queryKey) return;
    const sessionId = current.id;
    if (current.ai.status === "complete") return;
    if (requestsRef.current.ai) return requestsRef.current.ai.promise;

    let webResults;
    try {
      webResults = await loadWebResults(queryKey);
    } catch (error) {
      if (error.name !== "AbortError") {
        updateSession(queryKey, sessionId, (value) => ({
          ...value,
          ai: { ...value.ai, status: "error", error: value.web.error },
        }));
      }
      return;
    }

    if (
      !sessionRef.current ||
      sessionRef.current.query !== queryKey ||
      sessionRef.current.id !== sessionId
    ) return;
    const controller = new AbortController();
    updateSession(queryKey, sessionId, (value) => ({
      ...value,
      ai: { ...value.ai, status: "loading", error: "", streamingAnswer: "" },
    }));

    let completed = false;
    const promise = streamQuestion(queryKey, {
      signal: controller.signal,
      results: webResults,
      onEvent: (event) => {
        if (event.type === "chunk" && typeof event.text === "string") {
          updateSession(queryKey, sessionId, (value) => ({
            ...value,
            ai: {
              ...value.ai,
              streamingAnswer: value.ai.streamingAnswer + event.text,
            },
          }));
        } else if (event.type === "complete") {
          if (
            typeof event.answer !== "string" ||
            !Array.isArray(event.citations)
          ) {
            throw new Error("The search service returned an incomplete stream.");
          }
          completed = true;
          const currentConversation = conversationRef.current;
          if (
            currentConversation?.sessionId === sessionId &&
            currentConversation.messages.length === 0
          ) {
            commitConversation({
              ...currentConversation,
              messages: [
                createMessage("user", queryKey),
                createMessage("assistant", event.answer, {
                  citations: event.citations,
                  sourceCount: sessionRef.current?.web.results?.length,
                }),
              ],
            });
          }
          updateSession(queryKey, sessionId, (value) => ({
            ...value,
            ai: {
              summary: event.answer,
              citations: event.citations,
              streamingAnswer: "",
              status: "complete",
              error: "",
            },
          }));
        } else if (event.type === "error") {
          throw new Error(event.message || "The answer stream failed.");
        }
      },
    })
      .then(() => {
        if (!completed && !controller.signal.aborted) {
          throw new Error("The answer stream ended before completion.");
        }
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          updateSession(queryKey, sessionId, (value) => ({
            ...value,
            ai: {
              ...value.ai,
              status: "error",
              error: getRequestError(error),
              streamingAnswer: "",
            },
          }));
        }
      })
      .finally(() => {
        if (requestsRef.current.ai?.controller === controller) {
          requestsRef.current.ai = null;
        }
      });

    requestsRef.current.ai = { controller, promise };
    return promise;
  }

  function isCurrentConversationRequest(request) {
    return (
      requestsRef.current.conversation === request &&
      !request.controller.signal.aborted &&
      sessionRef.current?.id === request.sessionId &&
      conversationRef.current?.id === request.conversationId
    );
  }

  function generateConversationAnswer(userMessageId, assistantMessageId) {
    const activeSession = sessionRef.current;
    const activeConversation = conversationRef.current;
    if (!activeSession || !activeConversation) return;
    if (requestsRef.current.conversation) return;

    const userIndex = activeConversation.messages.findIndex(
      (message) => message.id === userMessageId,
    );
    if (userIndex < 0) return;
    const userMessage = activeConversation.messages[userIndex];
    const history = activeConversation.messages
      .slice(0, userIndex)
      .filter((message) => message.status === "complete" && message.content.trim())
      .map(({ role, content }) => ({
        role,
        content: content.slice(0, MAX_CONVERSATION_MESSAGE_LENGTH),
      }));
    const request = {
      controller: new AbortController(),
      sessionId: activeSession.id,
      conversationId: activeConversation.id,
      userMessageId,
      assistantMessageId,
    };

    updateConversation(request.sessionId, request.conversationId, (value) => ({
      ...value,
      messages: value.messages.map((message) =>
        message.id === assistantMessageId
          ? { ...message, content: "", citations: [], error: "", status: "streaming" }
          : message,
      ),
    }));
    requestsRef.current.conversation = request;

    request.promise = Promise.resolve()
      .then(async () => {
        const results = await loadWebResults(activeSession.query);
        if (!isCurrentConversationRequest(request)) return;

        let completed = false;
        let streamError = null;
        await streamQuestion(userMessage.content, {
          signal: request.controller.signal,
          results,
          conversationHistory: history,
          onEvent: (event) => {
            if (!isCurrentConversationRequest(request)) return;
            if (event.type === "chunk" && typeof event.text === "string") {
              updateConversation(request.sessionId, request.conversationId, (value) => ({
                ...value,
                messages: value.messages.map((message) =>
                  message.id === assistantMessageId
                    ? { ...message, content: message.content + event.text }
                    : message,
                ),
              }));
            } else if (event.type === "complete") {
              if (typeof event.answer !== "string" || !Array.isArray(event.citations)) {
                streamError = new Error("The search service returned an incomplete stream.");
                return;
              }
              completed = true;
              updateConversation(request.sessionId, request.conversationId, (value) => ({
                ...value,
                messages: value.messages.map((message) =>
                  message.id === assistantMessageId
                    ? {
                        ...message,
                        content: event.answer,
                        citations: event.citations,
                        sourceCount: results.length,
                        error: "",
                        status: "complete",
                      }
                    : message,
                ),
              }));
            } else if (event.type === "error") {
              streamError = new Error(event.message || "The answer stream failed.");
            }
          },
        });

        if (streamError) throw streamError;
        if (!completed && !request.controller.signal.aborted) {
          throw new Error("The answer stream ended before completion.");
        }
      })
      .catch((error) => {
        if (error.name === "AbortError" || request.controller.signal.aborted) return;
        if (!isCurrentConversationRequest(request)) return;
        updateConversation(request.sessionId, request.conversationId, (value) => ({
          ...value,
          messages: value.messages.map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: "", citations: [], error: getRequestError(error), status: "error" }
              : message,
          ),
        }));
      })
      .finally(() => {
        if (requestsRef.current.conversation === request) {
          requestsRef.current.conversation = null;
        }
      });

    return request.promise;
  }

  function handleConversationSend(content) {
    if (requestsRef.current.conversation) return;
    const current = conversationRef.current;
    const activeSession = sessionRef.current;
    if (!current || !activeSession || current.sessionId !== activeSession.id) return;
    if (activeSession.ai.status === "loading") return;

    const userMessage = createMessage("user", content);
    const assistantMessage = createMessage("assistant", "", {
      relatedUserId: userMessage.id,
      status: "streaming",
    });
    commitConversation({
      ...current,
      messages: [...current.messages, userMessage, assistantMessage],
    });
    generateConversationAnswer(userMessage.id, assistantMessage.id);
  }

  function handleRetryConversation(userMessageId, assistantMessageId) {
    if (requestsRef.current.conversation) return;
    generateConversationAnswer(userMessageId, assistantMessageId);
  }

  function handleCancelConversation() {
    const request = requestsRef.current.conversation;
    if (!request) return;
    requestsRef.current.conversation = null;
    request.controller.abort();
    updateConversation(request.sessionId, request.conversationId, (value) => ({
      ...value,
      messages: value.messages.map((message) =>
        message.id === request.assistantMessageId
          ? { ...message, content: "", citations: [], error: "", status: "cancelled" }
          : message,
      ),
    }));
  }

  function startNewSearch(queryKey) {
    cancelAllRequests();
    const nextSession = createSession(queryKey);
    commitSession(nextSession);
    commitConversation(createConversation(nextSession.id));
    setMode("all");
    loadWebResults(queryKey).catch(() => {});
    loadImageResults(queryKey).catch(() => {});
    loadAIAnswer(queryKey);
  }

  function handleSubmit(event) {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery) return;
    startNewSearch(trimmedQuery);
  }

  function handleModeChange(nextMode) {
    if (nextMode === mode) return;
    setMode(nextMode);
    const queryKey = sessionRef.current?.query;
    if (!queryKey) return;
    if (nextMode === "images") loadImageResults(queryKey).catch(() => {});
    if (nextMode === "ai") loadAIAnswer(queryKey);
  }

  function handleRetry() {
    const current = sessionRef.current;
    if (!current) return;
    if (mode === "images") loadImageResults(current.query).catch(() => {});
    else if (mode === "ai") loadAIAnswer(current.query);
    else if (current.web.status === "error") {
      loadWebResults(current.query).catch(() => {});
    } else {
      loadAIAnswer(current.query);
    }
  }

  function handleCancel() {
    const current = sessionRef.current;
    if (!current) return;
    const type =
      mode === "images"
        ? "images"
        : mode === "ai" || session?.ai.status === "loading"
          ? "ai"
          : "web";
    cancelRequest(type);
    updateSession(current.query, current.id, (value) => ({
      ...value,
      [type]: {
        ...value[type],
        status: type === "ai" ? "error" : "idle",
        ...(type === "ai"
          ? { error: "Answer generation was cancelled. Retry to continue." }
          : {}),
        ...(type === "ai" ? { streamingAnswer: "" } : {}),
      },
    }));
  }

  const activeBranch =
    session?.[
      mode === "images" ? "images" : mode === "ai" ? "ai" : "web"
    ];
  const isActiveLoading =
    activeBranch?.status === "loading" ||
    (mode === "all" && session?.ai.status === "loading");
  const loadingMessage =
    mode === "ai" || (mode === "all" && session?.ai.status === "loading")
      ? "Preparing your grounded AI answer..."
      : "Searching the web and preparing your answer...";
  const activeError =
    mode === "all" && session?.web.status !== "error"
      ? session?.ai
      : activeBranch;
  const activeConversation =
    conversation?.sessionId === session?.id ? conversation : null;
  const isConversationGenerating =
    session?.ai.status === "loading" ||
    Boolean(requestsRef.current.conversation) ||
    Boolean(activeConversation?.messages.some(
      (message) => message.role === "assistant" && message.status === "streaming",
    ));
  const showInitialStreamingAnswer =
    mode === "all" ||
    (mode === "ai" && activeConversation?.messages.length === 0);

  return (
    <main className="min-h-screen overflow-x-hidden bg-slate-950 text-slate-100">
      <Header productName={PRODUCT_NAME} />
      <section className="mx-auto flex min-h-[calc(100vh-73px)] w-full max-w-6xl flex-col items-center px-4 pb-20 pt-14 text-center sm:px-8 sm:pt-20">
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
            onClear={() => setQuery("")}
          />
          <SearchModeNav activeMode={mode} onChange={handleModeChange} />
          <div className="mt-5 flex flex-wrap justify-center gap-2.5" aria-label="Example queries">
            {EXAMPLE_QUERIES.map((example) => (
              <button
                className="min-h-10 rounded-full border border-slate-800 bg-slate-900 px-3.5 py-2 text-left text-xs text-slate-400 transition-colors hover:border-teal-500/60 hover:text-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 sm:text-sm"
                key={example}
                type="button"
                onClick={() => setQuery(example)}
              >
                {example}
              </button>
            ))}
          </div>
        </div>

        {isActiveLoading && (
          <LoadingState
            message={loadingMessage}
            onCancel={mode === "ai" ? undefined : handleCancel}
          />
        )}
        {mode !== "images" && session?.images.status === "loading" && (
          <LoadingState message="Preparing image results in the background..." />
        )}
        {mode !== "all" && session?.web.status === "loading" && (
          <LoadingState message="Preparing web results in the background..." />
        )}
        {showInitialStreamingAnswer && session?.ai.streamingAnswer && (
          <div className="mt-10 w-full max-w-2xl text-left" aria-live="polite">
            <AIAnswer
              summary={session.ai.streamingAnswer}
              sourceCount={session.web.results?.length}
            />
          </div>
        )}
        {activeError?.status === "error" && (
          <ErrorState message={activeError.error} onRetry={handleRetry} />
        )}

        {session && mode === "all" && session.web.status === "complete" && (
          <div className="mt-10 w-full max-w-2xl scroll-mt-6" ref={answerRef}>
            {session.ai.status === "complete" && (
              <AIAnswer
                summary={session.ai.summary}
                sourceCount={session.web.results?.length}
                citations={session.ai.citations}
              />
            )}
            <SearchResults
              results={session.web.results}
              totalResults={session.web.totalResults}
            />
          </div>
        )}
        {session && mode === "images" && session.images.status === "complete" && (
          <div className="mt-10 w-full max-w-2xl scroll-mt-6" ref={answerRef}>
            <ImageResults
              results={session.images.results}
              totalResults={session.images.totalResults}
            />
          </div>
        )}
        {session && mode === "ai" && activeConversation && (
          <div className="w-full scroll-mt-6" ref={answerRef}>
            <ConversationView
              key={activeConversation.id}
              messages={activeConversation.messages}
              isGenerating={isConversationGenerating}
              isInitialLoading={session.ai.status === "loading" && activeConversation.messages.length === 0}
              onSend={handleConversationSend}
              onCancel={requestsRef.current.conversation ? handleCancelConversation : handleCancel}
              onRetry={handleRetryConversation}
            />
          </div>
        )}
        {!session && (
          <p className="mt-16 text-xs text-slate-400">
            Explore ideas, understand topics, and find what matters.
          </p>
        )}
      </section>
    </main>
  );
}

export default App;
