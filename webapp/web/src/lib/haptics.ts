/**
 * Тактильная отдача на телефоне (Android / поддерживающие браузеры).
 * iOS Safari `navigator.vibrate` не реализует — там просто ничего не произойдёт,
 * поэтому вибрация всегда дублирует визуальный отклик, а не заменяет его.
 */
export function tapFeedback(durationMs = 8): void {
  if (typeof window === "undefined" || typeof navigator === "undefined") return;
  try {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!window.matchMedia("(max-width: 1023px)").matches) return;
    navigator.vibrate?.(durationMs);
  } catch {
    /* вибрация не критична */
  }
}

/** Подтверждающее действие (применить, сбросить, сменить тему) — заметнее выбора. */
export function confirmFeedback(): void {
  tapFeedback(15);
}
