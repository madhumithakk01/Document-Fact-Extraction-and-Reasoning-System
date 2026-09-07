interface BadgeProps {
  label: string;
  className?: string;
  dot?: string;
}

/** A small pill with a coloured dot and always a text label. */
export function Badge({ label, className = "", dot }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-meta ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />}
      {label}
    </span>
  );
}
