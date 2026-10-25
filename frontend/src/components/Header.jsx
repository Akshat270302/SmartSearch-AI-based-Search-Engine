import { Search } from "lucide-react";

function Header({ productName }) {
  return (
    <header className="mx-auto flex w-full max-w-6xl items-center justify-between border-b border-slate-900 px-4 py-4 sm:px-8 sm:py-5">
      <a
        className="inline-flex min-h-10 items-center gap-2.5 rounded-lg text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-4 focus-visible:ring-offset-slate-950"
        href="/"
        aria-label={`${productName} home`}
      >
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-teal-400 text-slate-950 shadow-[0_0_22px_rgba(45,212,191,0.18)]">
          <Search size={17} strokeWidth={2.5} aria-hidden="true" />
        </span>
        <span className="text-lg font-semibold tracking-tight">{productName}<span className="text-teal-400">.</span></span>
      </a>
      <a
        className="min-h-10 rounded-md px-3 py-2 text-sm text-slate-400 transition-colors duration-200 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-4 focus-visible:ring-offset-slate-950"
        href="#about"
      >
        About
      </a>
    </header>
  );
}

export default Header;
