/** Глобальный оверлей загрузки: не внутри AppShell — иначе remount страницы сбрасывает скелетон. */

let pending = false;
let pendingHref: string | null = null;
let pageLoading = false;
/** Успели ли увидеть loading=true у новой страницы после клика. */
let sawLoading = false;
let clearTimer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function cancelClearTimer() {
  if (clearTimer == null) return;
  clearTimeout(clearTimer);
  clearTimer = null;
}

export function getNavLoading(): boolean {
  return pending;
}

export function getPageLoading(): boolean {
  return pageLoading;
}

/** Показывать скелетон: переход или загрузка данных раздела. */
export function getShowSkeleton(): boolean {
  return pending || pageLoading;
}

/** Целевой путь клика — для подсветки пункта меню до смены pathname. */
export function getNavPendingHref(): string | null {
  return pendingHref;
}

export function setPageLoading(next: boolean): void {
  if (pageLoading === next) return;
  pageLoading = next;
  emit();
}

export function setNavLoading(next: boolean, href?: string | null): void {
  if (next) {
    const nextHref = href ?? pendingHref;
    if (pending && pendingHref === nextHref) return;
    cancelClearTimer();
    pending = true;
    pendingHref = nextHref;
    sawLoading = false;
    emit();
    return;
  }
  if (!pending && pendingHref == null) return;
  cancelClearTimer();
  pending = false;
  pendingHref = null;
  sawLoading = false;
  emit();
}

/**
 * Синхронизация со страницей.
 * Нельзя снимать pending только по `!loading`: при soft-nav URL меняется раньше
 * смены страницы, старый экран ещё с loading=false — скелетон моргал.
 */
export function syncNavLoadingWithPage(loading: boolean, pathname: string): void {
  if (!pending) return;

  if (loading) {
    cancelClearTimer();
    if (!sawLoading) {
      sawLoading = true;
    }
    return;
  }

  if (sawLoading) {
    setNavLoading(false);
    return;
  }

  const arrived =
    !!pendingHref &&
    (pathname === pendingHref || pathname.startsWith(`${pendingHref}/`));
  if (!arrived) return;

  cancelClearTimer();
  clearTimer = setTimeout(() => {
    clearTimer = null;
    if (pending && !sawLoading) setNavLoading(false);
  }, 120);
}

export function subscribeNavLoading(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
