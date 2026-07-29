export type NavItem = {
  id: string;
  href: string;
  label: string;
  /** Ready page vs placeholder */
  ready?: boolean;
};

export type NavSection = {
  id: string;
  title: string;
  items: NavItem[];
};

/** Блоки меню как на ai.conall.ru (REPORT_CATEGORIES). */
export const NAV_SECTIONS: NavSection[] = [
  {
    id: "developer",
    title: "Девелоперские проекты",
    items: [
      {
        id: "developer-projects",
        href: "/developer-projects",
        label: "Девелоперские проекты",
      },
    ],
  },
  {
    id: "finance",
    title: "Финансы",
    items: [
      { id: "bdds", href: "/finance/bdds", label: "БДДС (расходы)" },
      { id: "bdr", href: "/finance/bdr", label: "БДР (расходы)" },
      {
        id: "approved-budget",
        href: "/finance/approved-budget",
        label: "Утверждённый бюджет план/факт",
      },
      {
        id: "bdds-plan-fact",
        href: "/finance/bdds-plan-fact",
        label: "БДДС расходы (план, факт, уточненный план)",
      },
    ],
  },
  {
    id: "timeline",
    title: "Сроки",
    items: [
      {
        id: "control-points",
        href: "/timeline/control-points",
        label: "Контрольные точки",
      },
      {
        id: "project-schedule",
        href: "/timeline/project-schedule",
        label: "График проекта",
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
    title: "Проектные работы",
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
    title: "ГДРС",
    items: [
      { id: "gdrs-people", href: "/gdrs/people", label: "ГДРС (люди)" },
      {
        id: "gdrs-equipment",
        href: "/gdrs/equipment",
        label: "ГДРС (техника)",
      },
    ],
  },
  {
    id: "prescriptions",
    title: "Предписания",
    items: [
      {
        id: "prescriptions-contractors",
        href: "/prescriptions",
        label: "Предписания по подрядчикам",
      },
    ],
  },
  {
    id: "executive",
    title: "Исполнительная документация",
    items: [
      {
        id: "executive-docs",
        href: "/executive-docs",
        label: "Исполнительная документация",
      },
    ],
  },
  {
    id: "debit-credit",
    title: "Дебиторская и кредиторская задолженность",
    items: [
      {
        id: "debit-credit",
        href: "/debit-credit",
        label: "Дебиторская и кредиторская задолженность подрядчиков",
        ready: true,
      },
    ],
  },
];

export function findNavItem(
  pathname: string,
): { section: NavSection; item: NavItem } | null {
  for (const section of NAV_SECTIONS) {
    for (const item of section.items) {
      if (pathname === item.href || pathname.startsWith(`${item.href}/`)) {
        return { section, item };
      }
    }
  }
  return null;
}

export function allNavItems(): NavItem[] {
  return NAV_SECTIONS.flatMap((s) => s.items);
}
