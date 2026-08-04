"use client";

import { createContext, useContext, type ReactNode } from "react";

/**
 * На телефоне графики по умолчанию не перехватывают жесты: одним пальцем
 * листается страница. Зум и панорама доступны в развёрнутом виде, который
 * включает этот контекст. На desktop значение не используется.
 */
const ChartInteractiveContext = createContext(false);

export function ChartInteractiveProvider({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  return (
    <ChartInteractiveContext.Provider value={active}>
      {children}
    </ChartInteractiveContext.Provider>
  );
}

export function useChartInteractive(): boolean {
  return useContext(ChartInteractiveContext);
}
