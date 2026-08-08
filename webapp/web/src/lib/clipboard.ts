/**
 * Копирование в буфер без ожидания промиса: вызов остаётся внутри
 * пользовательского жеста, иначе часть браузеров отклоняет и clipboard,
 * и execCommand. `execCommand` — запасной путь для http-стенда.
 */
export function copyTextSync(text: string): boolean {
  try {
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* ниже execCommand */
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}
