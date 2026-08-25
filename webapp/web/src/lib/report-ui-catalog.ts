/** Каталог фильтров и виджетов UI ACL (зеркало API report_ui_catalog). */

export type ReportUiCatalogItem = {
  id: string;
  label: string;
};

export type ReportUiCatalogScreen = {
  nav_id: string;
  title: string;
  filters: ReportUiCatalogItem[];
  widgets: ReportUiCatalogItem[];
};

const FINANCE_FILTERS: ReportUiCatalogItem[] = [
  { id: "projects", label: "Проект" },
  { id: "date_from", label: "Период с" },
  { id: "date_to", label: "Период по" },
  { id: "group", label: "Группировать по" },
  { id: "view", label: "Представление" },
  { id: "show_deviation", label: "Показать отклонение" },
  { id: "hide_zero", label: "Скрывать нулевые месяцы" },
];

const FINANCE_WIDGETS: ReportUiCatalogItem[] = [
  { id: "kpi", label: "Сводка (KPI)" },
  { id: "chart_period", label: "График по периодам" },
  { id: "table_period", label: "Таблица по периодам" },
  { id: "chart_project", label: "График по проектам" },
  { id: "table_project", label: "Таблица по проектам" },
];

const GDRS_FILTERS: ReportUiCatalogItem[] = [
  { id: "projects", label: "Проект" },
  { id: "contractors", label: "Контрагент" },
  { id: "months", label: "Месяц" },
  { id: "plan_agg", label: "Агрегация план" },
  { id: "skud_agg", label: "Агрегация СКУД" },
  { id: "dyn_agg", label: "Агрегация динамики" },
  { id: "only_with_plan", label: "Только с планом" },
];

const GDRS_WIDGETS: ReportUiCatalogItem[] = [
  { id: "kpi", label: "Сводка (KPI)" },
  { id: "chart_projects", label: "График по проектам" },
  { id: "table_projects", label: "Таблица по проектам" },
  { id: "pie", label: "Распределение (pie)" },
  { id: "dynamics", label: "Динамика" },
  { id: "matrix", label: "Матрица" },
];

export const REPORT_UI_CATALOG: ReportUiCatalogScreen[] = [
  {
    nav_id: "bdds",
    title: "БДДС (расходы)",
    filters: FINANCE_FILTERS,
    widgets: FINANCE_WIDGETS,
  },
  {
    nav_id: "bdr",
    title: "БДР (расходы)",
    filters: FINANCE_FILTERS,
    widgets: FINANCE_WIDGETS,
  },
  {
    nav_id: "working-documentation",
    title: "Рабочая документация",
    filters: [
      { id: "projects", label: "Проект" },
      { id: "sections", label: "Раздел" },
      { id: "statuses", label: "Статус" },
      { id: "periodMode", label: "Период" },
      { id: "dateFrom", label: "Дата с" },
      { id: "dateTo", label: "Дата по" },
      { id: "metricMode", label: "Метрика" },
      { id: "showForecast", label: "Прогноз" },
      { id: "viewMode", label: "Отображение" },
    ],
    widgets: [
      { id: "kpi", label: "KPI-карточки" },
      { id: "pie", label: "Исполнение РД (pie)" },
      { id: "dynamics", label: "Динамика по месяцам" },
      { id: "delay_chart", label: "Просрочка выдачи" },
      { id: "tables", label: "Таблицы" },
    ],
  },
  {
    nav_id: "gdrs-people",
    title: "ГДРС (люди)",
    filters: GDRS_FILTERS,
    widgets: GDRS_WIDGETS,
  },
  {
    nav_id: "gdrs-equipment",
    title: "ГДРС (техника)",
    filters: GDRS_FILTERS,
    widgets: GDRS_WIDGETS,
  },
  {
    nav_id: "developer-projects",
    title: "Девелоперские проекты",
    filters: [{ id: "projects", label: "Проект" }],
    widgets: [
      { id: "kpi", label: "Сводка" },
      { id: "matrix", label: "Матрица контрольных точек" },
    ],
  },
  {
    nav_id: "prescriptions",
    title: "Предписания",
    filters: [
      { id: "projects", label: "Проект" },
      { id: "contractors", label: "Подрядчик" },
      { id: "contract_q", label: "Поиск договора" },
      { id: "date_from", label: "Дата с" },
      { id: "date_to", label: "Дата по" },
      { id: "hide_resolved", label: "Скрыть устранённые" },
    ],
    widgets: [
      { id: "kpi", label: "KPI / статусы" },
      { id: "chart_status", label: "График по статусам" },
      { id: "chart_objects", label: "График по объектам" },
      { id: "table", label: "Таблица предписаний" },
    ],
  },
];

export function getReportUiCatalog(
  navId: string,
): ReportUiCatalogScreen | undefined {
  return REPORT_UI_CATALOG.find((s) => s.nav_id === navId);
}
