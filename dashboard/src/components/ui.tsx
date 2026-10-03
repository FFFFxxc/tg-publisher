import type { ReactNode } from "react";

const COLORS: Record<string, string> = {
  candidate: "bg-sky-900/60 text-sky-300 border-sky-700",
  pending: "bg-amber-900/60 text-amber-300 border-amber-700",
  processing: "bg-violet-900/60 text-violet-300 border-violet-700",
  published: "bg-emerald-900/60 text-emerald-300 border-emerald-700",
  failed: "bg-red-900/60 text-red-300 border-red-700",
  ambiguous: "bg-orange-900/60 text-orange-300 border-orange-700",
  skipped: "bg-zinc-800 text-zinc-400 border-zinc-700",
  expired: "bg-zinc-800 text-zinc-500 border-zinc-700",
  unchecked: "bg-zinc-800 text-zinc-400 border-zinc-700",
  generated: "bg-emerald-900/60 text-emerald-300 border-emerald-700",
  not_needed: "bg-zinc-800 text-zinc-500 border-zinc-700",
  no_preview: "bg-zinc-800 text-zinc-500 border-zinc-700",
  manual: "bg-zinc-800 text-zinc-400 border-zinc-700",
  parsed: "bg-sky-900/60 text-sky-300 border-sky-700",
  repost: "bg-fuchsia-900/60 text-fuchsia-300 border-fuchsia-700",
  error: "bg-red-900/60 text-red-300 border-red-700",
  warning: "bg-amber-900/60 text-amber-300 border-amber-700",
  info: "bg-zinc-800 text-zinc-400 border-zinc-700",
  completed: "bg-emerald-900/60 text-emerald-300 border-emerald-700",
  pending_action: "bg-amber-900/60 text-amber-300 border-amber-700",
};

export function Badge({ v, children }: { v: string; children?: ReactNode }) {
  const cls = COLORS[v] ?? "bg-zinc-800 text-zinc-300 border-zinc-700";
  return (
    <span className={`inline-block whitespace-nowrap rounded border px-1.5 py-0.5 text-xs ${cls}`}>
      {children ?? v}
    </span>
  );
}

export function Card({ title, right, children }: { title?: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-[#10131a] p-4">
      {(title || right) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-zinc-300">{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-[#10131a] p-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="mt-1 break-words text-lg font-semibold text-zinc-100">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-zinc-500">{hint}</div>}
    </div>
  );
}

export function Dot({ ok }: { ok: boolean }) {
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`} />;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-800 bg-red-950/50 p-4 text-sm text-red-300">
      Ошибка: {message}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">
      {children}
    </div>
  );
}

export function Th({ children }: { children: ReactNode }) {
  return (
    <th className="border-b border-zinc-800 px-2 py-1.5 text-left text-xs font-medium text-zinc-500">{children}</th>
  );
}

export function Td({ children, className }: { children: ReactNode; className?: string }) {
  return <td className={`border-b border-zinc-900 px-2 py-1.5 align-top text-sm ${className ?? ""}`}>{children}</td>;
}

export const INPUT =
  "rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200 outline-none focus:border-sky-700";
