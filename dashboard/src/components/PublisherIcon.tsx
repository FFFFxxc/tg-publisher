import type { ReactNode } from "react";

const SHAPES = {
  plane: <path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13"/>,
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/></>,
  shield: <><path d="M12 22c5-2 8-5 8-10V5c-3 0-6-1-8-3-2 2-5 3-8 3v7c0 5 3 8 8 10Z"/><path d="m8.5 12 2.5 2.5 4.5-5"/></>,
  bot: <><rect x="4" y="7" width="16" height="12" rx="3"/><path d="M12 3v4M8 19v2m8-2v2M8 12h.1m7.9 0h.1"/></>,
  check: <><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></>,
  channel: <><circle cx="12" cy="11" r="2"/><path d="M6 17a8 8 0 1 1 12 0M3 20a12 12 0 1 1 18 0M12 13v8"/></>,
  queue: <><rect x="3" y="4" width="5" height="5" rx="1"/><rect x="3" y="15" width="5" height="5" rx="1"/><path d="M12 5h9m-9 4h5m-5 7h9m-9 4h5"/></>,
  pulse: <path d="M2 12h5l3-7 4 14 3-7h5"/>,
  warning: <><path d="M10.3 4.4a2 2 0 0 1 3.4 0l8 14.1a2 2 0 0 1-1.7 3H4a2 2 0 0 1-1.7-3l8-14.1Z"/><path d="M12 9v4m0 4h.01"/></>,
  photo: <><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m4 17 4-4 3 3 4-5 5 6"/></>,
  heart: <path d="M20.8 5.9a4.5 4.5 0 0 0-6.4 0L12 8.3 9.6 5.9a4.5 4.5 0 0 0-6.4 6.4L12 21l8.8-8.7a4.5 4.5 0 0 0 0-6.4Z"/>,
  swap: <path d="M4 8h15m-4-4 4 4-4 4m5 4H5m4-4-4 4 4 4"/>,
  arrow: <path d="M6 18 18 6M8 6h10v10"/>,
} satisfies Record<string, ReactNode>;

export type PublisherIconName = keyof typeof SHAPES;

export default function PublisherIcon({ name }: { name: PublisherIconName }) {
  return <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{SHAPES[name]}</svg>;
}
