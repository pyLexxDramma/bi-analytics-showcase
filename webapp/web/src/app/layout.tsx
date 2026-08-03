import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BI Analytics Showcase — Next",
  description: "Пилот миграции Streamlit → Next.js + FastAPI",
};

const themeInitScript = `(function(){try{var t=localStorage.getItem('bi_showcase_theme_v3');if(t==='dark')document.documentElement.classList.add('dark');else document.documentElement.classList.remove('dark');}catch(e){document.documentElement.classList.remove('dark');}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
