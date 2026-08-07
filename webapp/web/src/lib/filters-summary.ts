/**
 * Сводка активных фильтров для мобильного вида: счётчик на кнопке «Фильтры»
 * и ряд чипов под ней. На данные не влияет — только описание текущего выбора.
 */
export type ActiveFilter = {
  key: string;
  label: string;
  /** Снять один фильтр. Без обработчика чип рендерится без крестика. */
  onClear?: () => void;
};

const MAX_CHIP_TEXT = 26;

export function shortChipText(value: string, max = MAX_CHIP_TEXT): string {
  const s = (value || "").trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}…`;
}

/** «Проект: ЖК Ромашка» с усечением длинного значения. */
export function filterChip(
  key: string,
  name: string,
  value: string,
  onClear?: () => void,
): ActiveFilter {
  return { key, label: `${name}: ${shortChipText(value)}`, onClear };
}

/**
 * Чипы для мультивыбора: до `maxItems` значений отдельными чипами,
 * остаток сворачивается в «+N».
 */
export function multiFilterChips(
  key: string,
  name: string,
  values: string[],
  onChange: (next: string[]) => void,
  maxItems = 2,
): ActiveFilter[] {
  if (!values.length) return [];
  const shown = values.slice(0, maxItems);
  const chips = shown.map((v) =>
    filterChip(`${key}:${v}`, name, v, () =>
      onChange(values.filter((x) => x !== v)),
    ),
  );
  const rest = values.length - shown.length;
  if (rest > 0) {
    chips.push({
      key: `${key}:rest`,
      label: `${name}: +${rest}`,
      onClear: () => onChange(shown),
    });
  }
  return chips;
}

/** Дата в чипе — как в интерфейсе: 31.07.2026. */
export function formatDateChip(iso: string): string {
  const m = (iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

type FilterValues = Record<string, unknown>;

export type FilterChipSpec = {
  key: string;
  name: string;
  /** `date` — формат 31.07.2026; `flag` — «вкл»/«выкл». */
  kind?: "date" | "flag";
  /** id значения → подпись из API (группировка, представление и т. п.). */
  label?: (value: string) => string;
  /** Значения, которые надо вернуть при снятии чипа (связанные фильтры). */
  clear?: FilterValues;
  /** Сколько значений мультивыбора показывать отдельными чипами. */
  maxItems?: number;
};

/**
 * Сравнивает текущее состояние фильтров с исходным и собирает чипы.
 * Значения не трогает — только описывает выбор и предлагает вернуть исходное.
 */
export function buildFilterChips(
  filters: FilterValues,
  initial: FilterValues,
  specs: FilterChipSpec[],
  apply: (patch: FilterValues) => void,
): ActiveFilter[] {
  const out: ActiveFilter[] = [];
  for (const spec of specs) {
    const value = filters[spec.key];
    const base = initial[spec.key];
    const reset = () => apply(spec.clear ?? { [spec.key]: base });

    if (Array.isArray(value)) {
      const values = value.filter((v): v is string => typeof v === "string");
      out.push(
        ...multiFilterChips(
          spec.key,
          spec.name,
          values,
          (next) => apply({ [spec.key]: next }),
          spec.maxItems ?? 2,
        ),
      );
      continue;
    }

    if (value === base) continue;

    if (typeof value === "boolean") {
      out.push(filterChip(spec.key, spec.name, value ? "вкл" : "выкл", reset));
      continue;
    }

    if (typeof value === "string" && value) {
      const text =
        spec.kind === "date" ? formatDateChip(value) : spec.label?.(value) ?? value;
      out.push(filterChip(spec.key, spec.name, text, reset));
    }
  }
  return out;
}
