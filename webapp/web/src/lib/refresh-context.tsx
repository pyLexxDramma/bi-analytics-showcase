"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { usePullToRefresh } from "@/lib/use-pull-to-refresh";

const RefreshContext = createContext(0);

/** Счётчик pull-to-refresh — добавьте в deps эффекта загрузки данных. */
export function useRefreshTick(): number {
  return useContext(RefreshContext);
}

export function PullRefreshProvider({ children }: { children: ReactNode }) {
  const [tick, setTick] = useState(0);
  usePullToRefresh(true, () => setTick((n) => n + 1));
  return (
    <RefreshContext.Provider value={tick}>{children}</RefreshContext.Provider>
  );
}
