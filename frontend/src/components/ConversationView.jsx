import { useEffect, useRef, useState } from "react";
import { MessageCircle, RefreshCw, Send, StopCircle } from "lucide-react";

import AIAnswer from "./AIAnswer";

function ConversationView({
  messages,
  isGenerating,
  isInitialLoading = false,
  onSend,
  onCancel,
  onRetry,
}) {
  const [draft, setDraft] = useState("");
  const latestMessageRef = useRef(null);

  useEffect(() => {
    latestMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function handleSubmit(event) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || isGenerating) return;
    setDraft("");
    onSend(content);
  }

  return (
    <section className="mx-auto mt-8 flex w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70 text-left shadow-xl">
      <header className="flex items-center border-b border-slate-800 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <MessageCircle size={17} className="text-teal-400" aria-hidden="true" />
          Conversation
        </div>
      </header>

      <div
        className="max-h-[min(58vh,640px)] min-h-48 space-y-5 overflow-y-auto p-4 sm:p-5"
        aria-live="polite"
        aria-relevant="additions text"
      >
        {messages.length === 0 ? (
          <div className="flex min-h-40 flex-col items-center justify-center text-center">
            <MessageCircle size={25} className="text-slate-600" aria-hidden="true" />
            <p className="mt-3 text-sm font-medium text-slate-300">
              {isInitialLoading ? "Preparing your first answer" : "Start a conversation"}
            </p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
              {isInitialLoading
                ? "Your initial search answer will appear here. You can ask a follow-up when it is ready."
                : "Ask a follow-up about this search. Your search results stay available as context."}
            </p>
          </div>
        ) : (
          messages.map((message) => (
            <article
              className={message.role === "user" ? "flex justify-end" : "flex justify-start"}
              key={message.id}
            >
              {message.role === "user" ? (
                <div className="max-w-[90%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md border border-teal-400/20 bg-teal-400/10 px-4 py-3 text-sm leading-6 text-slate-100 sm:max-w-[82%]">
                  {message.content}
                </div>
              ) : (
                <div className="w-full min-w-0">
                  {message.content ? (
                    <AIAnswer
                      summary={message.content}
                      sourceCount={message.sourceCount}
                      citations={message.citations}
                    />
                  ) : message.status === "streaming" ? (
                    <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-3 text-sm text-slate-400" role="status">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-teal-400" />
                      Thinking…
                    </div>
                  ) : null}

                  {message.status === "streaming" && message.content && (
                    <p className="mt-2 text-xs text-slate-500" role="status">Generating answer…</p>
                  )}
                  {message.status === "cancelled" && (
                    <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                      <span>Response cancelled. Your question is still here.</span>
                      <button
                        className="inline-flex min-h-8 items-center gap-1.5 rounded-md text-teal-300 hover:text-teal-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
                        type="button"
                        onClick={() => onRetry(message.relatedUserId, message.id)}
                      >
                        <RefreshCw size={13} aria-hidden="true" /> Retry
                      </button>
                    </div>
                  )}
                  {message.status === "error" && (
                    <div className="mt-2 rounded-lg border border-rose-400/20 bg-rose-950/30 p-3">
                      <p className="text-sm text-rose-200">{message.error || "The answer could not be generated."}</p>
                      <button
                        className="mt-2 inline-flex min-h-8 items-center gap-1.5 text-xs font-medium text-rose-200 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
                        type="button"
                        onClick={() => onRetry(message.relatedUserId, message.id)}
                      >
                        <RefreshCw size={13} aria-hidden="true" /> Retry response
                      </button>
                    </div>
                  )}
                </div>
              )}
            </article>
          ))
        )}
        <div ref={latestMessageRef} />
      </div>

      <form className="border-t border-slate-800 bg-slate-950/60 p-3 sm:p-4" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor="conversation-message">Ask a follow-up question</label>
        <div className="flex items-end gap-2">
          <textarea
            id="conversation-message"
            className="min-h-11 min-w-0 flex-1 resize-y rounded-xl border border-slate-700 bg-slate-900 px-3.5 py-3 text-sm leading-5 text-slate-100 outline-none placeholder:text-slate-500 focus:border-teal-400/70 focus:ring-1 focus:ring-teal-400/40 disabled:opacity-60"
            rows={1}
            maxLength={4000}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask a follow-up…"
            disabled={isGenerating}
          />
          {isGenerating ? (
            <button
              className="inline-flex h-11 shrink-0 items-center gap-2 rounded-xl border border-rose-400/30 bg-rose-950/40 px-3 text-sm font-medium text-rose-200 hover:bg-rose-950/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
              type="button"
              onClick={onCancel}
            >
              <StopCircle size={16} aria-hidden="true" />
              <span className="hidden sm:inline">Cancel</span>
            </button>
          ) : (
            <button
              className="inline-flex h-11 shrink-0 items-center gap-2 rounded-xl bg-teal-400 px-3.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
              type="submit"
              disabled={!draft.trim()}
            >
              <Send size={15} aria-hidden="true" />
              <span className="hidden sm:inline">Send</span>
            </button>
          )}
        </div>
      </form>
    </section>
  );
}

export default ConversationView;
