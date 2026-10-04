"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const NAV = [
  { href: "/", label: "Главная", short: "Обзор", group: "Управление", icon: "home" },
  { href: "/sources", label: "Источники", short: "Источники", group: "Контент", icon: "source" },
  { href: "/queue", label: "Очередь публикаций", short: "Очередь", group: "Контент", icon: "queue" },
  { href: "/own-posts", label: "Архив канала", short: "Архив", group: "Контент", icon: "archive" },
  { href: "/schedule", label: "Расписание", short: "Расписание", group: "Автоматизация", icon: "calendar" },
  { href: "/accounts", label: "Аккаунты для актива", short: "Аккаунты", group: "Автоматизация", icon: "users" },
  { href: "/additional", label: "Дополнительно", short: "Доп.", group: "Автоматизация", icon: "network" },
  { href: "/ai", label: "Нейросеть", short: "Нейросеть", group: "Автоматизация", icon: "spark" },
  { href: "/footer", label: "Подпись к постам", short: "Подпись", group: "Автоматизация", icon: "edit" },
  { href: "/activity", label: "Журнал работы", short: "Журнал", group: "Контроль", icon: "activity" },
] as const;

function Icon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    home: <><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5M9 21v-7h6v7"/></>,
    source: <><circle cx="6" cy="12" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="m8 11 8-4M8 13l8 4"/></>,
    queue: <><path d="M5 6h14M5 12h14M5 18h9"/><circle cx="3" cy="6" r=".5"/><circle cx="3" cy="12" r=".5"/><circle cx="3" cy="18" r=".5"/></>,
    archive: <><path d="M4 7h16v13H4zM3 4h18v3H3z"/><path d="M9 11h6"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/></>,
    spark: <><path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3Z"/><path d="m18 15 .8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8L18 15Z"/></>,
    edit: <><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/></>,
    activity: <><path d="M4 19V5M4 19h17"/><path d="m7 15 4-4 3 2 5-6"/></>,
    users: <><circle cx="9" cy="8" r="3"/><path d="M3 20c0-4 2-6 6-6s6 2 6 6"/><circle cx="17" cy="9" r="2.5"/><path d="M15 15c3.7-.5 6 1.2 6 5"/></>,
    network: <><circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="m10.7 7.2-4.4 8.6M13.3 7.2l4.4 8.6M7.5 18h9"/></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]">{paths[name]}</svg>;
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const groups = [...new Set(NAV.map((item) => item.group))];
  const active = (href: string) => href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand" aria-label="На главную">
          <span className="brand-mark">T</span>
          <span><strong>Publisher</strong><small>Управление каналом</small></span>
        </Link>
        <nav aria-label="Основная навигация" className="sidebar-nav">
          {groups.map((group) => (
            <div key={group} className="nav-group">
              <div className="nav-group-label">{group}</div>
              {NAV.filter((item) => item.group === group).map((item) => (
                <Link key={item.href} href={item.href} aria-current={active(item.href) ? "page" : undefined} className={`nav-link ${active(item.href) ? "nav-link-active" : ""}`}>
                  <Icon name={item.icon} /><span>{item.label}</span>
                </Link>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">Управление Telegram-каналом</div>
      </aside>
      <div className="mobile-header">
        <Link href="/" className="brand"><span className="brand-mark">T</span><strong>Publisher</strong></Link>
        <span className="mobile-context">Панель управления</span>
      </div>
      <nav className="mobile-nav" aria-label="Навигация на мобильном устройстве">
        {NAV.map((item) => <Link key={item.href} href={item.href} aria-current={active(item.href) ? "page" : undefined} className={`mobile-nav-link ${active(item.href) ? "mobile-nav-link-active" : ""}`}><Icon name={item.icon}/><span>{item.short}</span></Link>)}
      </nav>
      <main className="main-content">{children}</main>
    </div>
  );
}
