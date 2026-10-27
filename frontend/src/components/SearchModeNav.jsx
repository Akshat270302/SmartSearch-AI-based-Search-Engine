const MODES = [
  ["ai", "AI Mode"],
  ["all", "All"],
  ["images", "Images"],
];

function SearchModeNav({ activeMode, onChange, disabled = false }) {
  return (
    <nav
      className="mt-4 flex w-full items-center gap-1 overflow-x-auto border-b border-slate-800"
      aria-label="Search type"
    >
      {MODES.map(([mode, label]) => (
        <button
          className={`min-h-11 shrink-0 border-b-2 px-4 text-sm font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-inset ${
            activeMode === mode
              ? "border-teal-400 text-teal-300"
              : "border-transparent text-slate-500 hover:text-slate-200"
          }`}
          key={mode}
          type="button"
          onClick={() => onChange(mode)}
          disabled={disabled}
          aria-current={activeMode === mode ? "page" : undefined}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}

export default SearchModeNav;
