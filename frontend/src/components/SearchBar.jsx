import { Search as SearchIcon, X } from "lucide-react";

function SearchBar({ value, onChange, onSubmit, onClear, disabled = false }) {
  return (
    <form
      className="flex w-full min-w-0 items-center gap-2 overflow-hidden rounded-2xl border border-slate-700/80 bg-slate-900/95 p-2 shadow-[0_18px_45px_-24px_rgba(0,0,0,0.8)] transition-[border-color,box-shadow] duration-200 focus-within:border-teal-400/70 focus-within:shadow-[0_18px_48px_-20px_rgba(20,184,166,0.24)]"
      onSubmit={onSubmit}
    >
      <label className="sr-only" htmlFor="search-query">
        Search query
      </label>
      <SearchIcon
        className="ml-3 shrink-0 text-slate-500"
        size={21}
        aria-hidden="true"
      />
      <input
        id="search-query"
        className="min-w-0 flex-1 bg-transparent px-1 py-3 text-base text-slate-100 outline-none placeholder:text-slate-500"
        type="search"
        value={value}
        onChange={onChange}
        placeholder="Ask anything..."
        disabled={disabled}
        aria-busy={disabled}
      />
      {value && !disabled && (
        <button
          className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-slate-500 transition-colors duration-200 hover:bg-slate-800 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
          type="button"
          onClick={onClear}
          aria-label="Clear search query"
        >
          <X size={17} aria-hidden="true" />
        </button>
      )}
      <button
        className="grid h-11 w-11 min-w-0 shrink-0 place-items-center rounded-xl bg-teal-400 text-slate-950 transition-colors duration-200 hover:bg-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-600 sm:w-auto sm:gap-2 sm:px-4"
        type="submit"
        disabled={disabled || !value.trim()}
      >
        <span className="whitespace-nowrap">Search</span>
      </button>
    </form>
  );
}

export default SearchBar;
