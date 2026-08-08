"use client";

import { useEffect, useState } from "react";
import { fetchAdminDataStatus, type AdminDataStatus } from "@/lib/api";

/**
 * Статус данных нужен и сайдбару, и плашке у заголовка. Общий кеш с одним
 * «полётом» запроса: экран не дёргает `/api/admin/data-status` дважды.
 */

type Listener = (status: AdminDataStatus | null) => void;

let cache: AdminDataStatus | null = null;
let inflight: Promise<AdminDataStatus> | null = null;
const listeners = new Set<Listener>();

export function setDataStatus(status: AdminDataStatus | null): void {
  cache = status;
  listeners.forEach((listener) => listener(status));
}

export function loadDataStatus(force = false): Promise<AdminDataStatus | null> {
  if (!force && cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = fetchAdminDataStatus();
    inflight.finally(() => {
      inflight = null;
    });
  }
  return inflight
    .then((status) => {
      setDataStatus(status);
      return status;
    })
    .catch(() => {
      setDataStatus(null);
      return null;
    });
}

export function useDataStatus(): AdminDataStatus | null {
  const [status, setStatus] = useState<AdminDataStatus | null>(cache);

  useEffect(() => {
    listeners.add(setStatus);
    void loadDataStatus();
    return () => {
      listeners.delete(setStatus);
    };
  }, []);

  return status;
}
