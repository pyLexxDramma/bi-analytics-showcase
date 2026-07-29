import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BI Analytics Showcase — Next",
  description: "Пилот миграции Streamlit → Next.js + FastAPI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  );
}
