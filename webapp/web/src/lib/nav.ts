export type NavItem = {
  id: string;
  href: string;
  label: string;
  ready?: boolean;
};

/** Группа-аккордеон в блоке «Отчёты» (как на ai.conall.ru). */
export type ReportAccordion = {
  id: string;
  label: string;
  items: NavItem[];
};

/** Одиночный отчёт без вложенности. */
export type ReportLeaf = {
  id: string;
  href: string;
  label: string;
  ready?: boolean;
  /** Подсветка как активная вкладка (зелёная). */
  kind?: "tab" | "link";
};

export const REPORT_TOP_TAB: ReportLeaf = {
  id: "developer-projects",
  href: "/developer-projects",
  label: "Девелоперские проекты",
  ready: true,
  kind: "tab",
};

export const REPORT_ACCORDIONS: ReportAccordion[] = [
  {
    id: "finance",
    label: "Финансы",
    items: [
      { id: "bdds", href: "/finance/bdds", label: "БДДС (расходы)", ready: true },
      { id: "bdr", href: "/finance/bdr", label: "БДР (расходы)", ready: true },
      {
        id: "approved-budget",
        href: "/finance/approved-budget",
        label: "Утверждённый бюджет план/факт",
        ready: true,
      },
      {
        id: "bdds-plan-fact",
        href: "/finance/bdds-plan-fact",
        label: "БДДС расходы (план, факт, уточненный план)",
        ready: true,
      },
    ],
  },
  {
    id: "timeline",
    label: "Сроки",
    items: [
      {
        id: "control-points",
        href: "/timeline/control-points",
        label: "Контрольные точки",
        ready: true,
      },
      {
        id: "project-schedule",
        href: "/timeline/project-schedule",
        label: "График проекта",
        ready: true,
      },
      {
        id: "deviation-reasons",
        href: "/timeline/deviation-reasons",
        label: "Причины отклонений",
      },
      {
        id: "baseline-deviation",
        href: "/timeline/baseline-deviation",
        label: "Отклонение от базового плана",
      },
    ],
  },
  {
    id: "project-docs",
    label: "Проектные работы",
    items: [
      {
        id: "project-documentation",
        href: "/docs/project-documentation",
        label: "Проектная документация",
      },
      {
        id: "working-documentation",
        href: "/docs/working-documentation",
        label: "Рабочая документация",
      },
    ],
  },
  {
    id: "gdrs",
    label: "ГДРС",
    items: [
      { id: "gdrs-people", href: "/gdrs/people", label: "ГДРС (люди)" },
      {
        id: "gdrs-equipment",
        href: "/gdrs/equipment",
        label: "ГДРС (техника)",
      },
    ],
  },
];

export const REPORT_STANDALONE: ReportLeaf[] = [
  {
    id: "prescriptions",
    href: "/prescriptions",
    label: "Предписания по подрядчикам",
    kind: "link",
  },
  {
    id: "executive-docs",
    href: "/executive-docs",
    label: "Исполнительная документация",
    kind: "link",
  },
  {
    id: "debit-credit",
    href: "/debit-credit",
    label: "Дебиторская и кредиторская задолженность подрядчиков",
    ready: true,
    kind: "link",
  },
];

/** @deprecated use REPORT_* — оставлено для home page */
export type NavSection = {
  id: string;
  title: string;
  items: NavItem[];
};

export const NAV_SECTIONS: NavSection[] = [
  {
    id: "developer",
    title: "Девелоперские проекты",
    items: [REPORT_TOP_TAB],
  },
  ...REPORT_ACCORDIONS.map((a) => ({
    id: a.id,
    title: a.label,
    items: a.items,
  })),
  {
    id: "standalone",
    title: "Прочее",
    items: REPORT_STANDALONE,
  },
];

export function accordionIdForPath(pathname: string): string | null {
  for (const acc of REPORT_ACCORDIONS) {
    if (acc.items.some((i) => pathname === i.href || pathname.startsWith(`${i.href}/`))) {
      return acc.id;
    }
  }
  return null;
}

export function findNavItem(pathname: string): NavItem | ReportLeaf | null {
  if (
    pathname === REPORT_TOP_TAB.href ||
    pathname.startsWith(`${REPORT_TOP_TAB.href}/`)
  ) {
    return REPORT_TOP_TAB;
  }
  for (const acc of REPORT_ACCORDIONS) {
    for (const item of acc.items) {
      if (pathname === item.href || pathname.startsWith(`${item.href}/`)) {
        return item;
      }
    }
  }
  for (const item of REPORT_STANDALONE) {
    if (pathname === item.href || pathname.startsWith(`${item.href}/`)) {
      return item;
    }
  }
  return null;
}
