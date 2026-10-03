import "./globals.css";
import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";

export const metadata = {
  title: "Publisher · управление каналом",
  description: "Панель управления публикациями Telegram-канала",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body><AppShell>{children}</AppShell></body>
    </html>
  );
}
