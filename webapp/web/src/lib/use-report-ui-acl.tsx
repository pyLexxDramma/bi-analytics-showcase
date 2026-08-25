"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fetchReportUiAcl } from "@/lib/api";

export type ReportUiAclState = {
  filters: string[] | null;
  widgets: string[] | null;
  loading: boolean;
  isFilterAllowed: (key: string) => boolean;
  isWidgetAllowed: (id: string) => boolean;
};

const defaultState: ReportUiAclState = {
  filters: null,
  widgets: null,
  loading: false,
  isFilterAllowed: () => true,
  isWidgetAllowed: () => true,
};

const ReportUiAclContext = createContext<ReportUiAclState>(defaultState);

function buildHelpers(
  filters: string[] | null,
  widgets: string[] | null,
): Pick<ReportUiAclState, "isFilterAllowed" | "isWidgetAllowed"> {
  const filterSet = filters ? new Set(filters) : null;
  const widgetSet = widgets ? new Set(widgets) : null;
  return {
    isFilterAllowed: (key: string) => {
      if (!key || filterSet == null) return true;
      return filterSet.has(key);
    },
    isWidgetAllowed: (id: string) => {
      if (!id || widgetSet == null) return true;
      return widgetSet.has(id);
    },
  };
}

/** Fetch UI ACL for nav.id. null allowlist = all visible. */
export function useReportUiAcl(navId: string | undefined | null): ReportUiAclState {
  const [filters, setFilters] = useState<string[] | null>(null);
  const [widgets, setWidgets] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(Boolean(navId));

  useEffect(() => {
    if (!navId) {
      setFilters(null);
      setWidgets(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void fetchReportUiAcl(navId)
      .then((data) => {
        if (cancelled) return;
        setFilters(data.filters ?? null);
        setWidgets(data.widgets ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setFilters(null);
        setWidgets(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [navId]);

  const helpers = useMemo(
    () => buildHelpers(filters, widgets),
    [filters, widgets],
  );

  return {
    filters,
    widgets,
    loading,
    ...helpers,
  };
}

export function ReportUiAclProvider({
  navId,
  children,
}: {
  navId: string;
  children: ReactNode;
}) {
  const acl = useReportUiAcl(navId);
  return (
    <ReportUiAclContext.Provider value={acl}>
      {children}
    </ReportUiAclContext.Provider>
  );
}

export function useReportUiAclContext(): ReportUiAclState {
  return useContext(ReportUiAclContext);
}

/** Hide children when filterKey is not allowed (no-op if key omitted). */
export function AclFilterGate({
  filterKey,
  children,
}: {
  filterKey?: string;
  children: ReactNode;
}) {
  const { isFilterAllowed } = useReportUiAclContext();
  if (filterKey && !isFilterAllowed(filterKey)) return null;
  return <>{children}</>;
}

export function AclWidgetGate({
  widgetId,
  children,
}: {
  widgetId: string;
  children: ReactNode;
}) {
  const { isWidgetAllowed } = useReportUiAclContext();
  if (!isWidgetAllowed(widgetId)) return null;
  return <>{children}</>;
}

/** Stable callback for list filtering without re-subscribing. */
export function useIsFilterAllowed(navId: string) {
  const acl = useReportUiAcl(navId);
  return useCallback(
    (key: string) => acl.isFilterAllowed(key),
    [acl.isFilterAllowed],
  );
}
