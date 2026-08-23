"use client";

import { createContext, useContext } from "react";

const ReportAccessContext = createContext(true);

export function ReportAccessProvider({
  allowed,
  children,
}: {
  allowed: boolean;
  children: React.ReactNode;
}) {
  return (
    <ReportAccessContext.Provider value={allowed}>
      {children}
    </ReportAccessContext.Provider>
  );
}

/** false — AppShell скрыл контент («Нет доступа»); не дергать API отчёта. */
export function useReportAllowed(): boolean {
  return useContext(ReportAccessContext);
}
