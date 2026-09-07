import type { ReactNode } from "react";

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-hairline border-t-accent ${className}`}
    />
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
      <p className="text-section text-text-primary">{title}</p>
      {hint && <p className="max-w-sm text-meta text-text-muted">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="m-6 rounded border border-contradicts/40 bg-contradicts/5 p-4 text-cell text-contradicts">
      {message}
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="text-section text-text-primary">{children}</h2>
  );
}
