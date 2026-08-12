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
