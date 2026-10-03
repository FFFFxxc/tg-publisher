import "./globals.css";
import type { ReactNode } from "react";
import Link from "next/link";

const NAV: [string, string][] = [
  ["/", "Обзор"],
  ["/sources", "Источники"],
  ["/queue", "Очередь"],
  ["/schedule", "Расписание"],
  ["/ai", "AI"],
  ["/footer", "Подпись"],
  ["/own-posts", "Свои посты"],
  ["/activity", "Активность"],
];

export const metadata = {
  title: "tg-publisher · панель",
  description: "Панель управления tg-publisher",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <div className="flex min-h-screen">
          <nav className="w-52 shrink-0 space-y-1 border-r border-zinc-800 bg-[#0e1118] p-4">
            <div className="mb-4 px-2 text-base font-semibold text-zinc-100">tg-publisher</div>
            {NAV.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                className="block rounded px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              >
                {label}
              </Link>
            ))}
          </nav>
          <main className="max-w-6xl flex-1 p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
