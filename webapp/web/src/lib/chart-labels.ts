/** Убрать «Проект | …» в подписях, если в фильтре выбран один проект. */
export function stripProjectPrefixIfSingle(
  label: string,
  singleProject: boolean,
): string {
  if (!singleProject || !label) return label;
  const sep = " | ";
  const idx = label.indexOf(sep);
  if (idx < 0) return label;
  const rest = label.slice(idx + sep.length).trim();
  return rest || label;
}

/**
 * Уникальные ключи категорий Plotly при одинаковых подписях (иначе дубли
 * слипаются/двоятся на оси Y). В ticktext — исходный текст.
 */
export function uniquePlotCategories(labels: string[]): {
  keys: string[];
  texts: string[];
} {
  const seen = new Map<string, number>();
  const keys: string[] = [];
  const texts: string[] = [];
  for (const raw of labels) {
    const label = raw || "—";
    const n = (seen.get(label) ?? 0) + 1;
    seen.set(label, n);
    texts.push(label);
    keys.push(n === 1 ? label : `${label}\u200b${n}`);
  }
  return { keys, texts };
}

export function isSingleProjectSelection(
  project: string | string[] | null | undefined,
  allToken = "Все",
): boolean {
  if (project == null) return false;
  const list = Array.isArray(project)
    ? project.map((p) => String(p).trim()).filter(Boolean)
    : String(project)
        .split("|")
        .map((p) => p.trim())
        .filter(Boolean);
  const concrete = list.filter((p) => p && p !== allToken);
  return concrete.length === 1;
}
