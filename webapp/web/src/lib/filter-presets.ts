"use client";

export type FilterPreset = {
  id: string;
  name: string;
  /** Query string without leading `?` */
  query: string;
  savedAt: number;
};

const KEY = "bi_filter_presets_v1";
const MAX_PER_SCREEN = 8;

function readAll(): Record<string, FilterPreset[]> {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, FilterPreset[]>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeAll(data: Record<string, FilterPreset[]>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
  } catch {
    /* private mode */
  }
}

export function listFilterPresets(navId: string): FilterPreset[] {
  return readAll()[navId] ?? [];
}

export function saveFilterPreset(
  navId: string,
  name: string,
  query: string,
): FilterPreset {
  const trimmed = name.trim().slice(0, 48);
  const q = query.replace(/^\?/, "");
  const preset: FilterPreset = {
    id: `${Date.now()}`,
    name: trimmed || "Срез",
    query: q,
    savedAt: Date.now(),
  };
  const all = readAll();
  const list = [preset, ...(all[navId] ?? [])].slice(0, MAX_PER_SCREEN);
  all[navId] = list;
  writeAll(all);
  return preset;
}

export function deleteFilterPreset(navId: string, id: string): void {
  const all = readAll();
  all[navId] = (all[navId] ?? []).filter((p) => p.id !== id);
  writeAll(all);
}
