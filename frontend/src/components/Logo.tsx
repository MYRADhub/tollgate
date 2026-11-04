export function Logo({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect x="3" y="6" width="4" height="22" rx="1" fill="currentColor" />
      <rect x="25" y="6" width="4" height="22" rx="1" fill="currentColor" />
      <rect x="7" y="12" width="18" height="3.2" rx="1.6" fill="#818cf8" />
      <rect x="7" y="18" width="18" height="3.2" rx="1.6" fill="#818cf8" opacity="0.55" />
      <circle cx="5" cy="5" r="2.2" fill="#34d399" />
    </svg>
  );
}
