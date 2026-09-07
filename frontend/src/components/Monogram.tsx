import { hashHue, initials } from "@/lib/format";

export function Monogram({ name, size = 22 }: { name: string; size?: number }) {
  const hue = hashHue(name);
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded font-mono"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.42,
        color: `hsl(${hue} 45% 78%)`,
        background: `hsl(${hue} 30% 22%)`,
        border: `1px solid hsl(${hue} 30% 32%)`,
      }}
      title={name}
    >
      {initials(name)}
    </span>
  );
}
