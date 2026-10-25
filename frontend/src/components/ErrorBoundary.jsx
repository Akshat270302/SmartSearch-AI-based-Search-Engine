import { Component } from "react";

class ErrorBoundary extends Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="grid min-h-screen place-items-center bg-slate-950 px-5 text-slate-100">
          <section
            className="w-full max-w-md rounded-2xl border border-rose-400/25 bg-slate-900 p-6 text-center shadow-xl"
            role="alert"
          >
            <h1 className="text-lg font-semibold">SearchAI is temporarily unavailable</h1>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              An unexpected error occurred. Refresh the page and try again.
            </p>
            <button
              className="mt-5 min-h-10 rounded-lg bg-teal-400 px-4 py-2 text-sm font-medium text-slate-950 transition-colors hover:bg-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
              type="button"
              onClick={() => window.location.reload()}
            >
              Refresh page
            </button>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
