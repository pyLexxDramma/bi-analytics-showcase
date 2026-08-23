"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type Ctx = {
  activeKey: string | null;
  setActiveKey: (key: string | null) => void;
};

const ChartTableSyncContext = createContext<Ctx | null>(null);

/** Связка графика и таблицы: подсветка строки по категории на оси X. */
export function ChartTableSyncProvider({ children }: { children: ReactNode }) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const value = useMemo(
    () => ({ activeKey, setActiveKey }),
    [activeKey],
  );
  return (
    <ChartTableSyncContext.Provider value={value}>
      {children}
    </ChartTableSyncContext.Provider>
  );
}

export function useChartTableSync(): Ctx {
  const ctx = useContext(ChartTableSyncContext);
  if (!ctx) {
    return {
      activeKey: null,
      setActiveKey: () => {},
    };
  }
  return ctx;
}

/** Нормализация подписи оси / ячейки «Проект» для сопоставления. */
export function chartSyncKey(raw: unknown): string {
  return String(raw ?? "")
    .trim()
    .toLocaleLowerCase("ru-RU");
}

export function useChartTableRowClass(rowKey: string): string {
  const { activeKey } = useChartTableSync();
  if (!activeKey) return "";
  return chartSyncKey(rowKey) === activeKey ? "bi-chart-sync-row" : "";
}

export function useChartCategoryHandlers(category: string) {
  const { setActiveKey } = useChartTableSync();
  const key = chartSyncKey(category);
  const onEnter = useCallback(() => setActiveKey(key), [key, setActiveKey]);
  const onLeave = useCallback(() => setActiveKey(null), [setActiveKey]);
  return { onMouseEnter: onEnter, onMouseLeave: onLeave };
}

/** Строка таблицы с двусторонней подсветкой при sync график↔таблица. */
export function SyncTableRow({
  syncKey,
  className = "",
  children,
}: {
  syncKey: string;
  className?: string;
  children: ReactNode;
}) {
  const { setActiveKey } = useChartTableSync();
  const syncClass = useChartTableRowClass(syncKey);
  const key = chartSyncKey(syncKey);
  return (
    <tr
      className={`${className} ${syncClass}`.trim()}
      onMouseEnter={() => setActiveKey(key)}
      onMouseLeave={() => setActiveKey(null)}
    >
      {children}
    </tr>
  );
}
