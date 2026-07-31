# -*- coding: utf-8 -*-
"""Общая инфраструктура светлых превью-вкладок (только dev, не клиентский release)."""
from __future__ import annotations

LIGHT_PREVIEW_SUFFIX = " (превью — светлая)"

PROFILE_SETTINGS_LABEL = "Настройки профиля"
PROFILE_LIGHT_PREVIEW_SESSION_KEY = "_profile_light_preview"

ADMIN_PANEL_LABEL = "Административная панель"
ADMIN_LIGHT_PREVIEW_SESSION_KEY = "_admin_light_preview"

LOGIN_PAGE_LABEL = "Страница входа"
LOGIN_LIGHT_PREVIEW_SESSION_KEY = "_login_light_preview"

# style#id — отключаются на тёмной вкладке (media=not all), чтобы не «течь» между темами
LIGHT_PREVIEW_STYLE_TAG_IDS = (
    "gdrs-light-preview-css",
    "bi-light-filters-css",
    "bi-light-style-overrides",
    "bi-light-filters-live-css-v12",
    "bi-light-filters-live-css-v13",
    "bi-light-filters-live-css-v14",
    "bi-light-filters-live-css-v11",
    "bi-light-filters-live-css-v10",
    "bi-light-filters-live-css-v9",
    "bi-light-filters-live-css-v8",
    "bi-light-filters-live-css-v7",
    "bi-light-filters-live-css-v6",
    "bi-light-filters-live-css-v5",
    "bi-light-filters-live-css-v4",
    "bi-light-filters-live-css-v3",
    "bi-light-filters-live-css-v2",
    "bi-light-filters-live-css",
)


def preview_light_name(base: str) -> str:
    """Каноническое имя превью: «БДДС (превью — светлая)»."""
    b = str(base or "").strip()
    if not b:
        return LIGHT_PREVIEW_SUFFIX.strip()
    if b.casefold().endswith(LIGHT_PREVIEW_SUFFIX.casefold()):
        return b
    return f"{b}{LIGHT_PREVIEW_SUFFIX}"


def is_light_preview_report(report_name: str) -> bool:
    """True для любой вкладки «… (превью — светлая)» (в т.ч. ГДРС)."""
    n = str(report_name or "").strip().casefold()
    return "превью" in n and "светл" in n


def light_preview_reports_enabled() -> bool:
    """Показывать ли светлые превью в меню (False на ai.conall.ru / release)."""
    try:
        from config import show_light_preview_reports

        return bool(show_light_preview_reports())
    except Exception:
        return False


def filter_reports_hide_light_preview(report_names: list[str]) -> list[str]:
    if light_preview_reports_enabled():
        return list(report_names)
    return [n for n in report_names if not is_light_preview_report(n)]


def apply_light_table_constants() -> None:
    """Патч палитры HTML-таблиц и Plotly в ``utils`` (только на время превью-run)."""
    import utils as u

    u.TABLE_BG_COLOR = "#ffffff"
    u.TABLE_HEADER_BG_COLOR = "#f3f4f6"
    u.TABLE_GROUP_ROW_BG_COLOR = "#e8ecf1"
    u.TABLE_TOTAL_ROW_BG_COLOR = "#e5e7eb"
    u.TABLE_TEXT_COLOR = "#111827"
    u.TABLE_CELL_BORDER = "1px solid #cbd5e1"
    u.FINANCE_TABLE_CELL_BORDER = "1px solid #94a3b8"
    u.CHART_BG_COLOR = "rgba(255, 255, 255, 0.96)"
    u.CHART_GRID_COLOR = "rgba(148, 163, 184, 0.45)"
    u.CHART_AXIS_LINE_COLOR = "rgba(100, 116, 139, 0.65)"
    u.CHART_ZEROLINE_COLOR = "rgba(100, 116, 139, 0.55)"
    u.TABLE_TOTAL_ROW_FONT_CSS = (
        "font-weight:800;font-size:1.32em;text-transform:uppercase;"
        "letter-spacing:0.05em;color:#111827;"
    )
    u.TABLE_CELL_BORDER_CSS = f"border: {u.TABLE_CELL_BORDER};"


def apply_dark_table_constants() -> None:
    """Восстановить production-палитру ``utils`` (после светлого превью)."""
    import utils as u

    u.TABLE_BG_COLOR = "hsl(209,67%,12%)"
    u.TABLE_HEADER_BG_COLOR = "hsl(209, 72%, 6%)"
    u.TABLE_GROUP_ROW_BG_COLOR = "hsl(209, 70%, 7%)"
    u.TABLE_TOTAL_ROW_BG_COLOR = "hsl(208, 58%, 18%)"
    u.TABLE_TEXT_COLOR = "#ffffff"
    u.TABLE_CELL_BORDER = "1px solid #5a7a9a"
    u.FINANCE_TABLE_CELL_BORDER = "1px solid #7a9ec4"
    u.CHART_BG_COLOR = "rgba(18, 56, 92, 0.88)"
    u.CHART_GRID_COLOR = "rgba(148, 163, 184, 0.45)"
    u.CHART_AXIS_LINE_COLOR = "rgba(100, 116, 139, 0.65)"
    u.CHART_ZEROLINE_COLOR = "rgba(100, 116, 139, 0.55)"
    u.TABLE_TOTAL_ROW_FONT_CSS = (
        "font-weight:800;font-size:1.32em;text-transform:uppercase;"
        "letter-spacing:0.05em;color:#f8fbff;"
    )
    u.TABLE_CELL_BORDER_CSS = f"border: {u.TABLE_CELL_BORDER};"


def use_light_theme() -> bool:
    """Светлая тема по умолчанию (cutover). Откат: ``BI_ANALYTICS_DARK_THEME=1``."""
    try:
        from config import use_light_theme_globally

        if use_light_theme_globally():
            return True
    except Exception:
        pass
    return False


def is_profile_light_preview_active() -> bool:
    try:
        import streamlit as st

        return bool(st.session_state.get(PROFILE_LIGHT_PREVIEW_SESSION_KEY))
    except Exception:
        return False


def is_admin_light_preview_active() -> bool:
    try:
        import streamlit as st

        return bool(st.session_state.get(ADMIN_LIGHT_PREVIEW_SESSION_KEY))
    except Exception:
        return False


def _query_param_str(st, name: str) -> str:
    try:
        v = st.query_params.get(name, "")
    except Exception:
        return ""
    if isinstance(v, list):
        return str(v[0]).strip() if v else ""
    return str(v or "").strip()


def sync_login_light_preview_from_query(st) -> None:
    if not light_preview_reports_enabled():
        return
    login_light = _query_param_str(st, "login_light").casefold()
    login_preview = _query_param_str(st, "login_preview").casefold()
    if login_light in ("1", "true", "yes", "on") or login_preview == "light":
        st.session_state[LOGIN_LIGHT_PREVIEW_SESSION_KEY] = True
        st.session_state.pop(PROFILE_LIGHT_PREVIEW_SESSION_KEY, None)
        st.session_state.pop(ADMIN_LIGHT_PREVIEW_SESSION_KEY, None)
    elif login_light in ("0", "false", "no", "off"):
        st.session_state[LOGIN_LIGHT_PREVIEW_SESSION_KEY] = False


def is_login_light_preview_active() -> bool:
    try:
        import streamlit as st

        return bool(st.session_state.get(LOGIN_LIGHT_PREVIEW_SESSION_KEY))
    except Exception:
        return False


def clear_foreign_light_preview_keys(st, *, keep: str | None = None) -> None:
    for key in (
        PROFILE_LIGHT_PREVIEW_SESSION_KEY,
        ADMIN_LIGHT_PREVIEW_SESSION_KEY,
        LOGIN_LIGHT_PREVIEW_SESSION_KEY,
    ):
        if keep and key == keep:
            continue
        st.session_state.pop(key, None)


def is_light_preview_active() -> bool:
    """True, если текущая вкладка — светлое превью или включена глобальная светлая тема."""
    if use_light_theme():
        return True
    if is_profile_light_preview_active():
        return True
    if is_admin_light_preview_active():
        return True
    if is_login_light_preview_active():
        return True
    try:
        import streamlit as st

        return is_light_preview_report(str(st.session_state.get("current_dashboard") or ""))
    except Exception:
        return False


def finance_chart_label_color(*, dark: str = "#f0f4f8", light: str = "#111827") -> str:
    return light if is_light_preview_active() else dark


FINANCE_DEV_GREEN_DARK = "hsl(148,100%,63%)"
FINANCE_DEV_GREEN_LIGHT = "#166534"


def finance_dev_negative_color() -> str:
    """Минус / экономия в таблицах: на светлом фоне — тёмно-зелёный для контраста."""
    return FINANCE_DEV_GREEN_LIGHT if is_light_preview_active() else FINANCE_DEV_GREEN_DARK


def finance_chart_neutral_label_color() -> str:
    return finance_chart_label_color(dark="#f0f4f8", light="#374151")


def finance_chart_caption_color() -> str:
    return finance_chart_label_color(dark="#e8eef5", light="#374151")


def finance_chart_legend_text_color() -> str:
    return finance_chart_label_color(dark="#e2e8f0", light="#111827")


def maybe_inject_light_filter_widgets(st) -> None:
    """CSS для фильтров на светлом превью (после unified filters css)."""
    if not is_light_preview_active():
        return
    inject_light_filters_css(st)


def sync_light_preview_theme(st) -> None:
    """Синхронизация class gdrs-light-preview, light-CSS и inline-стилей JS с текущей вкладкой."""
    import streamlit.components.v1 as components

    light = is_light_preview_active()
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        _ctx = get_script_run_ctx()
        _run_id = getattr(_ctx, "script_run_id", None) if _ctx else None
    except Exception:
        _run_id = None
    if _run_id is not None and st.session_state.get("_bi_theme_sync_run") == _run_id:
        return
    if _run_id is not None:
        st.session_state["_bi_theme_sync_run"] = _run_id
    st.session_state["_bi_light_preview_dom"] = light

    _style_ids_js = ",".join(f'"{x}"' for x in LIGHT_PREVIEW_STYLE_TAG_IDS)
    _is_light_js = "true" if light else "false"
    components.html(
        """
<script>
(function(){
  var IS_LIGHT = __IS_LIGHT__;
  var LIGHT_STYLE_IDS = [__STYLE_IDS__];
  var HANDLE = "__BI_LIGHT_WIDGETS_FIX_V19__";
  function resolveDoc() {
    try {
      if (window.parent && window.parent.document && window.parent.document.body)
        return window.parent.document;
    } catch (e0) {}
    try {
      if (window.top && window.top.document && window.top.document.body)
        return window.top.document;
    } catch (e1) {}
    return document.body ? document : null;
  }
  var doc = resolveDoc();
  if (!doc || !doc.body) return;
  var hostWin = doc.defaultView || window.parent || window;
  function setLightStyleTags(enabled) {
    LIGHT_STYLE_IDS.forEach(function(id) {
      var el = doc.getElementById(id);
      if (!el) return;
      if (enabled) el.removeAttribute("media");
      else el.setAttribute("media", "not all");
    });
  }
  function cleanupLightPreview() {
    doc.documentElement.classList.remove("gdrs-light-preview");
    doc.body.classList.remove("gdrs-light-preview");
    doc.documentElement.removeAttribute("data-bi-dark-css-off");
    setLightStyleTags(false);
    LIGHT_STYLE_IDS.forEach(function(id) {
      if (id.indexOf("live-css") < 0) return;
      var el = doc.getElementById(id);
      if (el) el.remove();
    });
    doc.querySelectorAll("[data-bi-light]").forEach(function(el) {
      el.removeAttribute("data-bi-light");
      el.removeAttribute("style");
    });
    doc.querySelectorAll('[data-testid="stCheckbox"] label[data-baseweb="checkbox"]').forEach(function(lbl) {
      lbl.removeAttribute("style");
      lbl.querySelectorAll("p, [data-testid='stMarkdownContainer'], [data-testid='stMarkdownContainer'] *, div").forEach(function(n) {
        n.removeAttribute("style");
      });
    });
    doc.querySelectorAll('div[data-baseweb="popover"] li, div[data-baseweb="popover"] [role="option"]').forEach(function(el) {
      el.removeAttribute("style");
      el.querySelectorAll("*").forEach(function(n) { n.removeAttribute("style"); });
    });
    doc.querySelectorAll("style[media='not all']").forEach(function(node) {
      var t = node.textContent || "";
      if (t.indexOf("#2a2a3a") >= 0 && t.indexOf(".stDateInput") >= 0) {
        node.removeAttribute("media");
      }
    });
    try {
      var prevOff = hostWin[HANDLE];
      if (prevOff && prevOff.obs && prevOff.obs.disconnect) prevOff.obs.disconnect();
      delete hostWin[HANDLE];
    } catch (eOff) {}
  }
  try {
    var prev = hostWin[HANDLE];
    if (prev) {
      if (prev.obs && prev.obs.disconnect) prev.obs.disconnect();
      if (prev.debounceTmr) clearTimeout(prev.debounceTmr);
    }
  } catch (eDisc) {}
  if (!IS_LIGHT) {
    cleanupLightPreview();
    return;
  }
  setLightStyleTags(true);
  doc.documentElement.classList.add("gdrs-light-preview");
  doc.body.classList.add("gdrs-light-preview");
  var cssId = "bi-light-filters-live-css-v15";
  ["bi-light-filters-live-css", "bi-light-filters-live-css-v2", "bi-light-filters-live-css-v3", "bi-light-filters-live-css-v4", "bi-light-filters-live-css-v5", "bi-light-filters-live-css-v6", "bi-light-filters-live-css-v7", "bi-light-filters-live-css-v8", "bi-light-filters-live-css-v9", "bi-light-filters-live-css-v10", "bi-light-filters-live-css-v11", "bi-light-filters-live-css-v12", "bi-light-filters-live-css-v13", "bi-light-filters-live-css-v14"].forEach(function(id) {
    var node = doc.getElementById(id);
    if (node) node.remove();
  });
  if (!doc.getElementById(cssId)) {
    var stEl = doc.createElement("style");
    stEl.id = cssId;
    stEl.textContent = [
      "html body.gdrs-light-preview .stDateInput > div > div > input,",
      "html body.gdrs-light-preview [data-testid=\\"stDateInput\\"] [data-baseweb=\\"input\\"],",
      "html body.gdrs-light-preview [data-testid=\\"stDateInput\\"] [data-baseweb=\\"input\\"] > div,",
      "html body.gdrs-light-preview [data-testid=\\"stDateInput\\"] [data-baseweb=\\"input\\"] input,",
      "html body.gdrs-light-preview [data-testid=\\"stDateInput\\"] input,",
      "html body.gdrs-light-preview [data-testid=\\"stDateInput\\"] button,",
      "html body.gdrs-light-preview .bi-filters-scope [data-testid=\\"stDateInput\\"] [data-baseweb=\\"input\\"],",
      "html body.gdrs-light-preview .bi-filters-scope [data-testid=\\"stDateInput\\"] [data-baseweb=\\"input\\"] > div,",
      "html body.gdrs-light-preview .bi-filters-scope [data-testid=\\"stDateInput\\"] button {",
      "background:#fff!important;background-color:#fff!important;",
      "color:#111827!important;-webkit-text-fill-color:#111827!important;",
      "border-color:#cbd5e1!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] {",
      "background:#fff!important;color:#111827!important;color-scheme:light!important;",
      "border:1px solid #cbd5e1!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] > div,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stVerticalBlock\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stVerticalBlockBorderWrapper\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stElementContainer\\"],",
      "html body.gdrs-light-preview [data-testid=\\"stPopoverBody\\"],",
      "html body.gdrs-light-preview [data-testid=\\"stPopoverBody\\"] [data-testid=\\"stVerticalBlock\\"] {",
      "background:#fff!important;background-color:#fff!important;color:#111827!important;",
      "color-scheme:light!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stPopover\\"] > button,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stDownloadButton\\"] button,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stDownloadButton\\"] a,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stButton\\"] button,",
      "html body.gdrs-light-preview [data-testid=\\"stPopoverBody\\"] [data-testid=\\"stDownloadButton\\"] button,",
      "html body.gdrs-light-preview [data-testid=\\"stPopoverBody\\"] [data-testid=\\"stDownloadButton\\"] a,",
      "html body.gdrs-light-preview [data-testid=\\"stPopoverBody\\"] [data-testid=\\"stButton\\"] button {",
      "background:#f8fafc!important;background-color:#f8fafc!important;",
      "color:#111827!important;-webkit-text-fill-color:#111827!important;",
      "border:1px solid #cbd5e1!important;font-weight:600!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stPopover\\"] > button:hover,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stDownloadButton\\"] button:hover,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stDownloadButton\\"] a:hover,",
      "html body.gdrs-light-preview [data-testid=\\"stPopoverBody\\"] [data-testid=\\"stDownloadButton\\"] button:hover,",
      "html body.gdrs-light-preview [data-testid=\\"stPopoverBody\\"] [data-testid=\\"stDownloadButton\\"] a:hover {",
      "background:#e5e7eb!important;color:#111827!important;border-color:#94a3b8!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stDownloadButton\\"] button *,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-testid=\\"stDownloadButton\\"] a *,",
      "html body.gdrs-light-preview [data-testid=\\"stPopoverBody\\"] [data-testid=\\"stDownloadButton\\"] button *,",
      "html body.gdrs-light-preview [data-testid=\\"stPopover\\"] > button * {",
      "color:#111827!important;-webkit-text-fill-color:#111827!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"datepicker\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [role=\\"grid\\"] {",
      "background:#fff!important;color:#111827!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"] button,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [role=\\"gridcell\\"] button {",
      "color:#111827!important;-webkit-text-fill-color:#111827!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"] {",
      "display:inline-flex!important;align-items:flex-start!important;gap:0.5rem!important;background:transparent!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"] p,",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"] [data-testid=\\"stMarkdownContainer\\"],",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"] [data-testid=\\"stMarkdownContainer\\"] * {",
      "background:transparent!important;background-color:transparent!important;color:#111827!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"] > input + div:not(:has(p)) {",
      "width:16px!important;height:16px!important;min-width:16px!important;max-width:16px!important;flex-shrink:0!important;",
      "display:flex!important;align-items:center!important;justify-content:center!important;",
      "border:2px solid #64748b!important;border-radius:4px!important;background:#fff!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"] > input + div:has(p) {",
      "background:transparent!important;border:none!important;width:auto!important;height:auto!important;",
      "max-width:none!important;display:inline-flex!important;align-items:flex-start!important;gap:0.5rem!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"] > input + div:has(p) > div:first-child:not(:has(p)) {",
      "width:16px!important;height:16px!important;min-width:16px!important;max-width:16px!important;flex-shrink:0!important;",
      "border:2px solid #64748b!important;border-radius:4px!important;background:#fff!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"]:has(input:checked) > input + div:not(:has(p)) {",
      "background:#2563eb!important;border-color:#2563eb!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"]:has(input:checked) > input + div:has(p) {",
      "background:transparent!important;background-color:transparent!important;border:none!important;",
      "width:auto!important;height:auto!important;max-width:none!important;display:inline-flex!important;gap:0.5rem!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"]:has(input:checked) > input + div:has(p) > div:first-child:not(:has(p)) {",
      "width:16px!important;height:16px!important;min-width:16px!important;max-width:16px!important;",
      "border:2px solid #2563eb!important;border-radius:4px!important;background:#2563eb!important;flex-shrink:0!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"]:has(input:checked) > div:has(p),",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"]:has(input:checked) p {",
      "background:transparent!important;background-color:transparent!important;color:#111827!important;}",
      "html body.gdrs-light-preview section.main div[data-testid=\\"stHorizontalBlock\\"]:has(> div[data-testid=\\"column\\"] [data-testid=\\"stCheckbox\\"]) > div[data-testid=\\"column\\"] {",
      "flex:1 1 14rem!important;min-width:11rem!important;width:auto!important;max-width:none!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stCheckbox\\"] label[data-baseweb=\\"checkbox\\"] p {",
      "white-space:normal!important;min-width:8rem!important;max-width:none!important;color:#111827!important;}",
      "html body.gdrs-light-preview .bi-filters-toggles [data-testid=\\"stRadio\\"] > div {",
      "flex-direction:row!important;flex-wrap:wrap!important;gap:0.75rem 1.25rem!important;}",
      "html body.gdrs-light-preview .bi-filters-toggles [data-testid=\\"stRadio\\"] label {",
      "background:transparent!important;margin:0!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stNumberInput\\"] input,",
      "html body.gdrs-light-preview [data-testid=\\"stTextInput\\"] input,",
      "html body.gdrs-light-preview div[data-testid=\\"stVerticalBlockBorderWrapper\\"] input {",
      "background:#fff!important;color:#111827!important;-webkit-text-fill-color:#111827!important;",
      "border-color:#cbd5e1!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] li,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] li span,",
      "html body.gdrs-light-preview div[data-baseweb=\\"menu\\"] li,",
      "html body.gdrs-light-preview div[data-baseweb=\\"menu\\"] li span {",
      "background:#fff!important;color:#111827!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"]:not(:has([data-baseweb=\\"calendar\\"])):not(:has([data-baseweb=\\"datepicker\\"])) li:hover,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"]:not(:has([data-baseweb=\\"calendar\\"])):not(:has([data-baseweb=\\"datepicker\\"])) li[data-highlighted=\\"true\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"]:not(:has([data-baseweb=\\"calendar\\"])):not(:has([data-baseweb=\\"datepicker\\"])) li[aria-selected=\\"true\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"menu\\"] li:hover,",
      "html body.gdrs-light-preview div[data-baseweb=\\"menu\\"] li[data-highlighted=\\"true\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"menu\\"] li[aria-selected=\\"true\\"] {",
      "background:#e5e7eb!important;background-color:#e5e7eb!important;color:#111827!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [role=\\"listbox\\"] [role=\\"option\\"][data-highlighted=\\"true\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [role=\\"listbox\\"] [role=\\"option\\"][aria-selected=\\"true\\"] {",
      "background:#e5e7eb!important;color:#111827!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"datepicker\\"],",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [role=\\"grid\\"] {",
      "background:#fff!important;color:#111827!important;color-scheme:light!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"] [role=\\"grid\\"] [role=\\"gridcell\\"] {",
      "background:transparent!important;color:#111827!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"] [role=\\"grid\\"] [role=\\"gridcell\\"]::before,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"] [role=\\"grid\\"] [role=\\"gridcell\\"]::after {",
      "content:none!important;display:none!important;background:transparent!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"] [role=\\"gridcell\\"]>div:first-child {",
      "width:2.25rem!important;height:2.25rem!important;margin:0 auto!important;",
      "display:inline-flex!important;align-items:center!important;justify-content:center!important;",
      "border-radius:9999px!important;color:#111827!important;background:transparent!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"] [role=\\"gridcell\\"]:hover>div:first-child,",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"] [role=\\"gridcell\\"][tabindex=\\"0\\"]>div:first-child {",
      "background:#f3f4f6!important;color:#111827!important;}",
      "html body.gdrs-light-preview div[data-baseweb=\\"popover\\"] [data-baseweb=\\"calendar\\"] [role=\\"gridcell\\"][data-bi-selected=\\"1\\"]>div:first-child {",
      "background:#2563eb!important;color:#fff!important;-webkit-text-fill-color:#fff!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stSidebar\\"] button[data-testid=\\"stBaseButton-primary\\"],",
      "html body.gdrs-light-preview [data-testid=\\"stSidebar\\"] [data-testid=\\"stButton\\"] button[data-testid=\\"stBaseButton-primary\\"] {",
      "background:linear-gradient(135deg,#ecfdf5 0%,#d1fae5 100%)!important;background-color:#ecfdf5!important;",
      "color:#111827!important;-webkit-text-fill-color:#111827!important;",
      "border:1.5px solid #6ee7b7!important;border-left:5px solid #16a34a!important;",
      "font-weight:700!important;box-shadow:0 1px 6px rgba(22,163,74,0.18)!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stSidebar\\"] button[data-testid=\\"stBaseButton-primary\\"] *,",
      "html body.gdrs-light-preview [data-testid=\\"stSidebar\\"] [data-testid=\\"stButton\\"] button[data-testid=\\"stBaseButton-primary\\"] * {",
      "color:#111827!important;-webkit-text-fill-color:#111827!important;font-weight:700!important;}",
      "html body.gdrs-light-preview [data-testid=\\"stSidebar\\"] p.sidebar-section-title,",
      "html body.gdrs-light-preview [data-testid=\\"stSidebar\\"] div[data-testid=\\"stMarkdownContainer\\"] p.sidebar-section-title {",
      "font-weight:800!important;color:#374151!important;-webkit-text-fill-color:#374151!important;}",
      "div[class*=\\"st-key-web_version_pick_scope\\"] [data-testid=\\"stSelectbox\\"] [data-baseweb=\\"select\\"] > div,",
      "div[class*=\\"st-key-web_version_pick_scope\\"] [data-testid=\\"stSelectbox\\"] div[data-baseweb=\\"select\\"] > div {",
      "border:2px solid #92400e!important;border-color:#92400e!important;border-radius:6px!important;",
      "box-shadow:0 0 0 1px rgba(146,64,14,0.12)!important;}",
    ].join("\\n");
    (doc.head || doc.body).appendChild(stEl);
  }
  function paintDateInputs() {
    doc.querySelectorAll('[data-testid="stDateInput"]').forEach(function(w) {
      w.querySelectorAll('[data-baseweb="input"], [data-baseweb="input"] > div, input, button').forEach(function(el) {
        if (el.closest('div[data-baseweb="popover"]')) return;
        if (el.getAttribute("data-bi-light") === "1") return;
        el.style.setProperty("background-color", "#ffffff", "important");
        el.style.setProperty("color", "#111827", "important");
        el.style.setProperty("-webkit-text-fill-color", "#111827", "important");
        el.style.setProperty("border-color", "#cbd5e1", "important");
        el.setAttribute("data-bi-light", "1");
      });
    });
  }
  function neutralizeCachedDarkCss() {
    if (doc.documentElement.getAttribute("data-bi-dark-css-off") === "1") return;
    doc.documentElement.setAttribute("data-bi-dark-css-off", "1");
    doc.querySelectorAll("style:not([id^='bi-light']):not([id='gdrs-light-preview-css'])").forEach(function(node) {
      var t = node.textContent || "";
      if (t.indexOf("#2a2a3a") >= 0 && t.indexOf(".stDateInput") >= 0) {
        node.setAttribute("media", "not all");
      }
    });
  }
  function isCalendarNode(el) {
    return !!(el && el.closest && el.closest('[data-baseweb="calendar"], [data-baseweb="datepicker"], [role="grid"]'));
  }
  function resetMenuItemPaint(el) {
    el.style.removeProperty("background-color");
    el.style.removeProperty("background");
    el.style.removeProperty("color");
    el.querySelectorAll("*").forEach(function(n) {
      n.style.removeProperty("background-color");
      n.style.removeProperty("background");
      n.style.removeProperty("color");
    });
  }
  function fixMenuHighlight() {
    doc.querySelectorAll('div[data-baseweb="popover"]').forEach(function(pop) {
      if (pop.querySelector('[data-baseweb="calendar"], [data-baseweb="datepicker"]')) return;
      pop.querySelectorAll('li, [role="option"]').forEach(function(el) {
        if (isCalendarNode(el)) return;
        var active = el.getAttribute("data-highlighted") === "true"
          || el.getAttribute("aria-selected") === "true";
        if (active) {
          el.style.setProperty("background-color", "#e5e7eb", "important");
          el.style.setProperty("color", "#111827", "important");
          el.querySelectorAll("*").forEach(function(n) {
            n.style.setProperty("background-color", "transparent", "important");
            n.style.setProperty("color", "#111827", "important");
          });
        } else {
          resetMenuItemPaint(el);
        }
      });
    });
  }
  function isSelectedDayLabel(label) {
    var l = (label || "").toLowerCase();
    return l.indexOf("selected") >= 0 || l.indexOf("выбран") >= 0 || l.indexOf("выбрано") >= 0;
  }
  function repaintCalendarDays() {
    doc.querySelectorAll('div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"]').forEach(function(cell) {
      var label = cell.getAttribute("aria-label") || "";
      if (isSelectedDayLabel(label)) cell.setAttribute("data-bi-selected", "1");
      else cell.removeAttribute("data-bi-selected");
    });
  }
  function ensureCalendarWatch() {
    doc.querySelectorAll('div[data-baseweb="popover"]').forEach(function(pop) {
      if (!pop.querySelector('[data-baseweb="calendar"]') || pop.getAttribute("data-bi-cal-watch")) return;
      pop.setAttribute("data-bi-cal-watch", "1");
      var tmr = null;
      new MutationObserver(function() {
        if (tmr) return;
        tmr = setTimeout(function() { tmr = null; repaintCalendarDays(); }, 20);
      }).observe(pop, {subtree: true, attributes: true, attributeFilter: ["aria-label", "tabindex", "class"]});
      repaintCalendarDays();
    });
  }
  function paintCalendarShell() {
    doc.querySelectorAll('div[data-baseweb="popover"]').forEach(function(pop) {
      if (!pop.querySelector('[data-baseweb="calendar"], [data-baseweb="datepicker"]')) return;
      pop.style.setProperty("background-color", "#ffffff", "important");
      pop.style.setProperty("color-scheme", "light", "important");
    });
  }
  function fixOpenPopover() {
    var calOpen = false;
    doc.querySelectorAll('div[data-baseweb="popover"]').forEach(function(pop) {
      if (pop.querySelector('[data-baseweb="calendar"], [data-baseweb="datepicker"]')) {
        calOpen = true;
        paintCalendarShell();
        ensureCalendarWatch();
        repaintCalendarDays();
      }
    });
    if (!calOpen) fixMenuHighlight();
  }
  var menuMoveTmr = null;
  function scheduleMenuFix() {
    if (menuMoveTmr) return;
    menuMoveTmr = setTimeout(function() {
      menuMoveTmr = null;
      var pop = doc.querySelector('div[data-baseweb="popover"]');
      if (!pop || pop.querySelector('[data-baseweb="calendar"], [data-baseweb="datepicker"]')) return;
      fixMenuHighlight();
    }, 24);
  }
  function fixCheckedCheckboxLabels() {
    doc.querySelectorAll('[data-testid="stCheckbox"] label[data-baseweb="checkbox"]').forEach(function(lbl) {
      var checked = !!lbl.querySelector('input[type="checkbox"]:checked');
      lbl.style.setProperty("background", "transparent", "important");
      lbl.style.setProperty("background-color", "transparent", "important");
      lbl.querySelectorAll("p, [data-testid='stMarkdownContainer'], [data-testid='stMarkdownContainer'] *").forEach(function(n) {
        n.style.setProperty("background", "transparent", "important");
        n.style.setProperty("background-color", "transparent", "important");
        n.style.setProperty("color", "#111827", "important");
      });
      lbl.querySelectorAll("div").forEach(function(div) {
        if (div.querySelector("p") || div.querySelector('[data-testid="stMarkdownContainer"]')) {
          div.style.setProperty("background", "transparent", "important");
          div.style.setProperty("background-color", "transparent", "important");
          div.style.setProperty("border", "none", "important");
        }
      });
      var input = lbl.querySelector('input[type="checkbox"]');
      if (!input) return;
      var box = input.nextElementSibling;
      if (!box || box.tagName !== "DIV") return;
      var hasText = !!(box.querySelector("p") || box.querySelector('[data-testid="stMarkdownContainer"]'));
      if (hasText) {
        box.style.setProperty("background", "transparent", "important");
        box.style.setProperty("background-color", "transparent", "important");
        box.style.setProperty("border", "none", "important");
        box.style.setProperty("width", "auto", "important");
        box.style.setProperty("height", "auto", "important");
        box.style.setProperty("max-width", "none", "important");
        box.style.setProperty("display", "inline-flex", "important");
        box.style.setProperty("gap", "0.5rem", "important");
        var indicator = box.firstElementChild;
        if (indicator && indicator.tagName === "DIV" && !indicator.querySelector("p")) {
          indicator.style.setProperty("width", "16px", "important");
          indicator.style.setProperty("height", "16px", "important");
          indicator.style.setProperty("min-width", "16px", "important");
          indicator.style.setProperty("max-width", "16px", "important");
          indicator.style.setProperty("flex-shrink", "0", "important");
          indicator.style.setProperty("border-radius", "4px", "important");
          indicator.style.setProperty("display", "flex", "important");
          indicator.style.setProperty("align-items", "center", "important");
          indicator.style.setProperty("justify-content", "center", "important");
          if (checked) {
            indicator.style.setProperty("background-color", "#2563eb", "important");
            indicator.style.setProperty("border", "2px solid #2563eb", "important");
          } else {
            indicator.style.setProperty("background-color", "#ffffff", "important");
            indicator.style.setProperty("border", "2px solid #64748b", "important");
          }
        }
        return;
      }
      box.style.setProperty("width", "16px", "important");
      box.style.setProperty("height", "16px", "important");
      box.style.setProperty("min-width", "16px", "important");
      box.style.setProperty("max-width", "16px", "important");
      box.style.setProperty("flex-shrink", "0", "important");
      if (checked) {
        box.style.setProperty("background-color", "#2563eb", "important");
        box.style.setProperty("border-color", "#2563eb", "important");
      } else {
        box.style.setProperty("background-color", "#ffffff", "important");
        box.style.setProperty("border-color", "#64748b", "important");
      }
    });
  }
  function tick() {
    neutralizeCachedDarkCss();
    paintDateInputs();
    fixCheckedCheckboxLabels();
  }
  tick();
  setTimeout(tick, 400);
  doc.addEventListener("click", function() {
    setTimeout(fixOpenPopover, 0);
    setTimeout(fixOpenPopover, 50);
    setTimeout(fixOpenPopover, 150);
    setTimeout(fixOpenPopover, 400);
  }, true);
  doc.addEventListener("keydown", function() { setTimeout(fixOpenPopover, 0); scheduleMenuFix(); }, true);
  doc.addEventListener("mousemove", scheduleMenuFix, true);
  doc.addEventListener("change", function(e) {
    if (e.target && e.target.type === "checkbox") fixCheckedCheckboxLabels();
  }, true);
  hostWin[HANDLE] = {};
})();
</script>
"""
        .replace("__IS_LIGHT__", _is_light_js)
        .replace("__STYLE_IDS__", _style_ids_js),
        height=0,
        scrolling=False,
    )


def inject_light_widgets_fix_js(st) -> None:
    """Обратная совместимость — делегирует sync_light_preview_theme."""
    sync_light_preview_theme(st)


def inject_light_filters_css(st) -> None:
    """Фильтры/чекбоксы/дата/календарь — светлая палитра (bi-filters-scope, expander)."""
    st.markdown(
        """
<style id="bi-light-filters-css">
/* Streamlit markdown-обёртки bi-filters-* не оборачивают виджеты — только :has() по DOM */
html body.gdrs-light-preview section.main [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stCheckbox"]) > div[data-testid="column"],
html body.gdrs-light-preview section.main div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stCheckbox"]) > div[data-testid="column"] {
  flex: 1 1 14rem !important;
  min-width: 11rem !important;
  max-width: none !important;
  width: auto !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] {
  display: inline-flex !important;
  flex-direction: row !important;
  align-items: flex-start !important;
  gap: 0.5rem !important;
  width: 100% !important;
  max-width: none !important;
  color: #111827 !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] p {
  flex: 1 1 auto !important;
  min-width: 8rem !important;
  width: auto !important;
  max-width: none !important;
  white-space: normal !important;
  word-break: normal !important;
  overflow-wrap: anywhere !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview .stCheckbox > label,
html body.gdrs-light-preview [data-testid="stCheckbox"] > label {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview .bi-filters-section-title,
html body.gdrs-light-preview .bi-filter-chip,
html body.gdrs-light-preview .bi-filter-chip b {
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
}
html body.gdrs-light-preview .bi-filter-chip {
  background: #f3f4f6 !important;
  border: 1px solid #cbd5e1 !important;
}
html body.gdrs-light-preview .bi-filter-chip b {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview .bi-filters-toggles {
  border-top-color: #e5e7eb !important;
}
/* Колонки чекбоксов: ui_quiet width:0 ломает подписи (по букве) */
html.gdrs-light-preview .bi-filters-toggles div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
html body.gdrs-light-preview .bi-filters-toggles div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
html body.gdrs-light-preview .bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stCheckbox"]) > div[data-testid="column"],
html body.gdrs-light-preview .bi-filters-toggles div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
  flex: 1 1 14rem !important;
  min-width: 10rem !important;
  width: auto !important;
  max-width: none !important;
}
html.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label,
html.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label p,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label p {
  white-space: normal !important;
  word-break: normal !important;
  overflow-wrap: anywhere !important;
  max-width: none !important;
  line-height: 1.35 !important;
}

/* Чекбоксы — квадрат сразу после input (как радио в gdrs_theme) */
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"],
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"] {
  display: inline-flex !important;
  flex-direction: row !important;
  align-items: flex-start !important;
  gap: 0.5rem !important;
  background: transparent !important;
  background-color: transparent !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > input,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > input {
  position: absolute !important;
  opacity: 0 !important;
  width: 1px !important;
  height: 1px !important;
  margin: 0 !important;
  pointer-events: none !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > input + div,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > input + div {
  width: 16px !important;
  height: 16px !important;
  min-width: 16px !important;
  min-height: 16px !important;
  max-width: 16px !important;
  margin-top: 2px !important;
  border: 2px solid #64748b !important;
  border-radius: 4px !important;
  background-color: #ffffff !important;
  box-sizing: border-box !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  flex-shrink: 0 !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:not(:has(input:checked)) > input + div:has(p),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:not(:has(input:checked)) > input + div:has(p),
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p) {
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  width: auto !important;
  height: auto !important;
  max-width: none !important;
  min-width: 0 !important;
  min-height: 0 !important;
  display: inline-flex !important;
  align-items: flex-start !important;
  gap: 0.5rem !important;
  flex-wrap: nowrap !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > input + div:has(p) > div:first-child:not(:has(p)),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > input + div:has(p) > div:first-child:not(:has(p)) {
  width: 16px !important;
  height: 16px !important;
  min-width: 16px !important;
  max-width: 16px !important;
  margin-top: 2px !important;
  border: 2px solid #64748b !important;
  border-radius: 4px !important;
  background-color: #ffffff !important;
  box-sizing: border-box !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  flex-shrink: 0 !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p) > div:first-child:not(:has(p)),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p) > div:first-child:not(:has(p)) {
  border-color: #2563eb !important;
  background-color: #2563eb !important;
}
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"] p,
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"] [data-testid="stMarkdownContainer"],
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"] [data-testid="stMarkdownContainer"] * {
  background: transparent !important;
  background-color: transparent !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:not(:has(p)),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:not(:has(p)) {
  border-color: #2563eb !important;
  background-color: #2563eb !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p) {
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  width: auto !important;
  height: auto !important;
  max-width: none !important;
  display: inline-flex !important;
  align-items: flex-start !important;
  gap: 0.5rem !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p) > div:first-child:not(:has(p)),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p) > div:first-child:not(:has(p)) {
  width: 16px !important;
  height: 16px !important;
  min-width: 16px !important;
  max-width: 16px !important;
  border: 2px solid #2563eb !important;
  border-radius: 4px !important;
  background-color: #2563eb !important;
  flex-shrink: 0 !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked),
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > div:has(p),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > div:has(p),
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) p,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) p {
  background: transparent !important;
  background-color: transparent !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > input + div > div,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > input + div > div {
  background-color: transparent !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:has(p),
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:has(p) {
  background: transparent !important;
  border: none !important;
  width: auto !important;
  max-width: none !important;
  min-width: 0 !important;
  height: auto !important;
  flex: 1 1 auto !important;
}
html body.gdrs-light-preview section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] svg,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"] svg {
  fill: #ffffff !important;
  color: #ffffff !important;
}

/* Чекбоксы: прозрачный фон строки */
html body.gdrs-light-preview [data-testid="stCheckbox"],
html body.gdrs-light-preview [data-testid="stCheckbox"] > label,
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"],
html body.gdrs-light-preview .bi-filters-scope [data-testid="stCheckbox"],
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"],
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"],
html body.gdrs-light-preview .bi-filters-scope [data-testid="stCheckbox"],
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"],
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] {
  background-color: transparent !important;
  background: transparent !important;
}
html body.gdrs-light-preview .bi-filters-scope [data-testid="stCheckbox"] label,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stCheckbox"] label p,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stCheckbox"] label span,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label p,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label span,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label p,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label span,
html body.gdrs-light-preview [data-testid="stExpander"] [data-testid="stWidgetLabel"],
html body.gdrs-light-preview [data-testid="stExpander"] [data-testid="stWidgetLabel"] p,
html body.gdrs-light-preview .bi-filters-selectors [data-testid="stWidgetLabel"],
html body.gdrs-light-preview .bi-filters-selectors [data-testid="stWidgetLabel"] p,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stCheckbox"] label,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stCheckbox"] label p,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stCheckbox"] label span,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label p,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stCheckbox"] label span,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label p,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label span,
html body.gdrs-light-preview [data-testid="stExpander"] [data-testid="stWidgetLabel"],
html body.gdrs-light-preview [data-testid="stExpander"] [data-testid="stWidgetLabel"] p,
html body.gdrs-light-preview .bi-filters-selectors [data-testid="stWidgetLabel"],
html body.gdrs-light-preview .bi-filters-selectors [data-testid="stWidgetLabel"] p {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  opacity: 1 !important;
}

/* Selectbox / multiselect: выпадающий список — hover и выделение в цвет светлой темы */
html body.gdrs-light-preview div[data-baseweb="popover"] ul,
html body.gdrs-light-preview div[data-baseweb="popover"] li,
html body.gdrs-light-preview div[data-baseweb="popover"] li span,
html body.gdrs-light-preview div[data-baseweb="menu"] li,
html body.gdrs-light-preview div[data-baseweb="menu"] li span {
  background-color: #ffffff !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"]:not(:has([data-baseweb="calendar"])):not(:has([data-baseweb="datepicker"])) li:hover,
html body.gdrs-light-preview div[data-baseweb="popover"]:not(:has([data-baseweb="calendar"])):not(:has([data-baseweb="datepicker"])) li[data-highlighted="true"],
html body.gdrs-light-preview div[data-baseweb="popover"]:not(:has([data-baseweb="calendar"])):not(:has([data-baseweb="datepicker"])) li[aria-selected="true"],
html body.gdrs-light-preview div[data-baseweb="menu"] li:hover,
html body.gdrs-light-preview div[data-baseweb="menu"] li[data-highlighted="true"],
html body.gdrs-light-preview div[data-baseweb="menu"] li[aria-selected="true"] {
  background-color: #e5e7eb !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] li[data-highlighted="true"] *,
html body.gdrs-light-preview div[data-baseweb="popover"] li[aria-selected="true"] *,
html body.gdrs-light-preview div[data-baseweb="menu"] li[data-highlighted="true"] * {
  background-color: transparent !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [role="listbox"] [role="option"][data-highlighted="true"],
html body.gdrs-light-preview div[data-baseweb="popover"] [role="listbox"] [role="option"][aria-selected="true"],
html body.gdrs-light-preview div[data-baseweb="popover"] ul[role="listbox"] ~ * [role="option"][data-highlighted="true"] {
  background-color: #e5e7eb !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview [data-testid="stCheckbox"] > [data-testid="stWidgetLabel"] {
  display: none !important;
}
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] {
  margin-bottom: 0.35rem !important;
}

/* Календарь (date_input range) — не смешивать с menu/select highlight */
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"],
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"],
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] > div,
html body.gdrs-light-preview div[data-baseweb="popover"] [role="grid"],
html body.gdrs-light-preview div[data-baseweb="popover"] [role="presentation"] {
  background-color: #ffffff !important;
  color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] > div:first-child,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"] > div:first-child,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] header {
  background-color: #f3f4f6 !important;
  color: #111827 !important;
}
/* BaseWeb Day = [role="gridcell"] (не button); чёрные блоки — ::before от darkenedBgMix15 */
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="grid"] [role="gridcell"] {
  background: transparent !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="grid"] [role="gridcell"]::before,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="grid"] [role="gridcell"]::after {
  content: none !important;
  display: none !important;
  background: transparent !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"] > div:first-child {
  width: 2.25rem !important;
  height: 2.25rem !important;
  margin: 0 auto !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  border-radius: 9999px !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  background: transparent !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"]:hover > div:first-child,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"][tabindex="0"] > div:first-child {
  background-color: #f3f4f6 !important;
  color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"][data-bi-selected="1"] > div:first-child {
  background-color: #2563eb !important;
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] span,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] p,
html body.gdrs-light-preview div[data-baseweb="popover"] [role="columnheader"] {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}

/* Период (st.date_input) — перебивает style.css + Streamlit dark theme */
html.gdrs-light-preview .stDateInput > div > div > input,
html.gdrs-light-preview [data-testid="stDateInput"] label,
html.gdrs-light-preview [data-testid="stDateInput"] [data-testid="stWidgetLabel"],
html.gdrs-light-preview [data-testid="stDateInput"] [data-testid="stWidgetLabel"] p,
html.gdrs-light-preview [data-testid="stDateInput"] label p,
html body.gdrs-light-preview [data-testid="stDateInput"] label,
html body.gdrs-light-preview [data-testid="stDateInput"] [data-testid="stWidgetLabel"],
html body.gdrs-light-preview [data-testid="stDateInput"] [data-testid="stWidgetLabel"] p,
html body.gdrs-light-preview [data-testid="stDateInput"] label p,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] label,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] [data-testid="stWidgetLabel"],
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] [data-testid="stWidgetLabel"] p {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="input"],
html.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="input"] > div,
html.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="input"] input,
html.gdrs-light-preview [data-testid="stDateInput"] input,
html.gdrs-light-preview [data-testid="stDateInput"] button,
html.gdrs-light-preview .stDateInput > div > div,
html.gdrs-light-preview .stDateInput > div > div > input,
html body.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="input"],
html body.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="input"] > div,
html body.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="input"] input,
html body.gdrs-light-preview [data-testid="stDateInput"] input,
html body.gdrs-light-preview .stDateInput > div > div,
html body.gdrs-light-preview .stDateInput > div > div > input,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] [data-baseweb="input"],
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] [data-baseweb="input"] > div,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] [data-baseweb="input"] input,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] input,
html body.gdrs-light-preview .bi-filters-scope .stDateInput > div > div,
html body.gdrs-light-preview .bi-filters-scope .stDateInput > div > div > input {
  background-color: #ffffff !important;
  background: #ffffff !important;
  color: #111827 !important;
  border-color: #cbd5e1 !important;
  -webkit-text-fill-color: #111827 !important;
}
html.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="input"]:focus-within,
html.gdrs-light-preview [data-testid="stDateInput"] input:focus,
html body.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="input"]:focus-within,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] [data-baseweb="input"]:focus-within {
  border-color: #2563eb !important;
  box-shadow: 0 0 0 1px #2563eb !important;
}
html.gdrs-light-preview [data-testid="stDateInput"] button,
html.gdrs-light-preview [data-testid="stDateInput"] [data-baseweb="button"],
html body.gdrs-light-preview [data-testid="stDateInput"] button,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] button {
  background-color: #ffffff !important;
  color: #111827 !important;
  border-color: #cbd5e1 !important;
}
html.gdrs-light-preview [data-testid="stDateInput"] svg,
html body.gdrs-light-preview [data-testid="stDateInput"] svg,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stDateInput"] svg {
  fill: #475569 !important;
  color: #475569 !important;
}

/* Popover календаря / «Скачать таблицу» (portaled к body) */
html.gdrs-light-preview div[data-baseweb="popover"],
html body.gdrs-light-preview div[data-baseweb="popover"] {
  background-color: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14) !important;
  color-scheme: light !important;
}
/* Внутренний блок Streamlit в popover (тёмная тема иначе даёт чёрный фон) */
html.gdrs-light-preview div[data-baseweb="popover"] > div,
html body.gdrs-light-preview div[data-baseweb="popover"] > div,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stVerticalBlock"],
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stVerticalBlockBorderWrapper"],
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stElementContainer"],
html body.gdrs-light-preview [data-testid="stPopoverBody"],
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stVerticalBlock"],
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stVerticalBlockBorderWrapper"],
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stElementContainer"] {
  background-color: #ffffff !important;
  background: #ffffff !important;
  color: #111827 !important;
  color-scheme: light !important;
}
html body.gdrs-light-preview [data-testid="stPopover"] > button,
html body.gdrs-light-preview [data-testid="stPopover"] button[data-testid^="stBaseButton"],
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stDownloadButton"] button,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stDownloadButton"] a,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stButton"] button,
html body.gdrs-light-preview div[data-baseweb="popover"] button[data-testid^="stBaseButton"],
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stDownloadButton"] button,
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stDownloadButton"] a,
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stButton"] button,
html body.gdrs-light-preview [data-testid="stPopoverBody"] button[data-testid^="stBaseButton"] {
  background-color: #f8fafc !important;
  background: #f8fafc !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border: 1px solid #cbd5e1 !important;
  font-weight: 600 !important;
}
html body.gdrs-light-preview [data-testid="stPopover"] > button:hover,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stDownloadButton"] button:hover,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stDownloadButton"] a:hover,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stButton"] button:hover,
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stDownloadButton"] button:hover,
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stDownloadButton"] a:hover,
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stButton"] button:hover {
  background-color: #e5e7eb !important;
  background: #e5e7eb !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border-color: #94a3b8 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stDownloadButton"] button *,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-testid="stDownloadButton"] a *,
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stDownloadButton"] button *,
html body.gdrs-light-preview [data-testid="stPopoverBody"] [data-testid="stDownloadButton"] a *,
html body.gdrs-light-preview [data-testid="stPopover"] > button * {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] > div:first-child,
html.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"] > div:first-child,
html.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] header,
html.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"] header,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] > div:first-child,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"] > div:first-child,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] header,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"] header {
  background-color: #f3f4f6 !important;
  color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] > div:first-child *,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"] > div:first-child *,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] header * {
  background-color: transparent !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"],
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"],
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] > div,
html body.gdrs-light-preview div[data-baseweb="popover"] [role="grid"],
html body.gdrs-light-preview div[data-baseweb="popover"] [role="presentation"] {
  background-color: #ffffff !important;
  color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] span,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] p,
html body.gdrs-light-preview div[data-baseweb="popover"] [role="columnheader"] {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="grid"] [role="gridcell"]::before,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="grid"] [role="gridcell"]::after {
  content: none !important;
  display: none !important;
  background: transparent !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"] > div:first-child {
  width: 2.25rem !important;
  height: 2.25rem !important;
  margin: 0 auto !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  border-radius: 9999px !important;
  color: #111827 !important;
  background: transparent !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"]:hover > div:first-child,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"][tabindex="0"] > div:first-child {
  background-color: #f3f4f6 !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] [role="gridcell"][data-bi-selected="1"] > div:first-child {
  background-color: #2563eb !important;
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
}
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="calendar"] svg,
html body.gdrs-light-preview div[data-baseweb="popover"] [data-baseweb="datepicker"] svg {
  fill: #475569 !important;
  color: #475569 !important;
}

html body.gdrs-light-preview .budget-deviation-table-wrap tr.bd-total-row td,
html body.gdrs-light-preview .bi-light-table .budget-deviation-table-wrap tr.bd-total-row td {
  background-color: #e5e7eb !important;
  color: #111827 !important;
}
html body.gdrs-light-preview .budget-deviation-table-wrap tr.bd-total-row td *,
html body.gdrs-light-preview .bi-light-table .budget-deviation-table-wrap tr.bd-total-row td * {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview .budget-deviation-table-wrap tr.bd-group-row td,
html body.gdrs-light-preview .bi-light-table .budget-deviation-table-wrap tr.bd-group-row td {
  background-color: #f3f4f6 !important;
  color: #111827 !important;
}
html body.gdrs-light-preview .budget-deviation-table-wrap tr.bd-total-row td {
  border-top: 3px solid #94a3b8 !important;
  border-bottom: 2px solid #cbd5e1 !important;
}
html body.gdrs-light-preview .budget-deviation-table-wrap tr.bd-group-row td {
  border-top: 1px solid #cbd5e1 !important;
}

/* Утверждённый бюджет план/факт — gauge+KPI (style.css не грузится на превью) */
html body.gdrs-light-preview {
  --appr-pf-gauge-h: 584px;
}
html body.gdrs-light-preview .appr-pf-summary-kpi {
  display: flex;
  gap: 1.25rem;
  flex-wrap: wrap;
  align-items: flex-start;
}
html body.gdrs-light-preview .appr-pf-summary-kpi-col {
  flex: 1 1 200px !important;
  min-width: 180px !important;
}
html body.gdrs-light-preview .appr-pf-summary-kpi .appr-pf-kpi-label {
  font-size: 2.3rem !important;
  font-weight: 800 !important;
  line-height: 1.1 !important;
}
html body.gdrs-light-preview .appr-pf-summary-kpi .appr-pf-kpi-value {
  font-size: 3.3rem !important;
  font-weight: 700 !important;
  line-height: 1.1 !important;
}
html body.gdrs-light-preview .appr-pf-summary-kpi .appr-pf-kpi-muted {
  font-size: 2.1rem !important;
  font-weight: 600 !important;
  line-height: 1.1 !important;
}
html body.gdrs-light-preview .appr-pf-summary-kpi .appr-pf-kpi-pct {
  font-size: 2.4rem !important;
  font-weight: 700 !important;
  line-height: 1.1 !important;
}
html body.gdrs-light-preview .appr-pf-summary-anchor ~ div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child div[data-testid="stHtml"],
html body.gdrs-light-preview .appr-pf-summary-anchor ~ div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stHtml"] iframe {
  min-height: var(--appr-pf-gauge-h) !important;
  max-height: var(--appr-pf-gauge-h) !important;
  height: var(--appr-pf-gauge-h) !important;
}

/* Прогнозный бюджет — редактор лотов и поля ввода (светлое превью) */
html body.gdrs-light-preview .fc-fc-lot-hdr-stick {
  background: #f8fafc !important;
  border-bottom: 2px solid #cbd5e1 !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08) !important;
}
html body.gdrs-light-preview .fc-fc-lot-hdr-stick th {
  color: #111827 !important;
}
html body.gdrs-light-preview .fc-fc-lot-name,
html body.gdrs-light-preview .fc-fc-lot-name *,
html body.gdrs-light-preview .main [data-testid="column"] [data-testid="stMarkdownContainer"] .fc-fc-lot-name,
html body.gdrs-light-preview .main [data-testid="column"] [data-testid="stMarkdownContainer"] .fc-fc-lot-name *,
html body.gdrs-light-preview .main [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] .fc-fc-lot-name,
html body.gdrs-light-preview .main [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] .fc-fc-lot-name *,
html body.gdrs-light-preview div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] .fc-fc-lot-name,
html body.gdrs-light-preview div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] .fc-fc-lot-name * {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stText"],
html body.gdrs-light-preview div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stText"] p {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview [data-baseweb="input"] input,
html body.gdrs-light-preview [data-testid="stTextInput"] input,
html body.gdrs-light-preview .stTextInput input,
html body.gdrs-light-preview [data-testid="stNumberInput"] input,
html body.gdrs-light-preview .stNumberInput input,
html body.gdrs-light-preview div[data-testid="stDataEditor"] input,
html body.gdrs-light-preview div[data-testid="stDataEditor"] textarea {
  color: #111827 !important;
  background-color: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  caret-color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview [data-testid="stSelectbox"] [data-baseweb="select"] > div,
html body.gdrs-light-preview [data-baseweb="select"] > div {
  background-color: #ffffff !important;
  border-color: #cbd5e1 !important;
  color: #111827 !important;
}
html body.gdrs-light-preview [data-testid="stSelectbox"] [data-baseweb="select"] span,
html body.gdrs-light-preview [data-baseweb="select"] span {
  color: #111827 !important;
}
html body.gdrs-light-preview [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
html body.gdrs-light-preview [data-testid="stMultiSelect"] [data-baseweb="select"] span,
html body.gdrs-light-preview .bi-filters-scope [data-testid="stMultiSelect"] [data-testid="stWidgetLabel"],
html body.gdrs-light-preview .bi-filters-scope [data-testid="stMultiSelect"] [data-testid="stWidgetLabel"] p {
  background-color: #ffffff !important;
  border-color: #cbd5e1 !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview div[data-testid="stElementContainer"]:has(iframe[title="streamlit_components_v1"]) {
  opacity: 1 !important;
  filter: none !important;
  mix-blend-mode: normal !important;
}
html body.gdrs-light-preview div[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: #cbd5e1 !important;
  background-color: #ffffff !important;
}
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stRadio"] label,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stRadio"] label p,
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stRadio"] label span {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stRadio"] > div {
  flex-direction: row !important;
  flex-wrap: wrap !important;
  gap: 0.75rem 1.25rem !important;
}
html body.gdrs-light-preview .bi-filters-toggles [data-testid="stRadio"] label {
  background: transparent !important;
  margin: 0 !important;
}
html body.gdrs-light-preview div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stNumberInput"] input,
html body.gdrs-light-preview div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stTextInput"] input,
html body.gdrs-light-preview div[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="input"] input {
  color: #111827 !important;
  background-color: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview [data-testid="stExpander"] [data-testid="stButton"] button,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stButton"] button {
  background-color: #f3f4f6 !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border: 1px solid #cbd5e1 !important;
  font-weight: 600 !important;
}
html body.gdrs-light-preview [data-testid="stExpander"] [data-testid="stButton"] button:hover,
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stButton"] button:hover {
  background-color: #e5e7eb !important;
  color: #111827 !important;
  border-color: #94a3b8 !important;
}
html body.gdrs-light-preview [data-testid="stMetricLabel"],
html body.gdrs-light-preview [data-testid="metric-container"] [data-testid="stMetricLabel"],
html body.gdrs-light-preview [data-testid="stMetric"] label {
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
}
html body.gdrs-light-preview [data-testid="stMetricValue"],
html body.gdrs-light-preview [data-testid="metric-container"] [data-testid="stMetricValue"] {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
/* KPI отклонения РД: цвет по знаку (выше общего stMetricValue светлой темы) */
html body.gdrs-light-preview .st-key-rd_dev_metric_pos [data-testid="stMetricValue"],
html body.gdrs-light-preview .st-key-rd_dev_metric_pos [data-testid="stMetricValue"] *,
html body.gdrs-light-preview .st-key-rd_dev_metric_pos [data-testid="metric-container"] [data-testid="stMetricValue"] {
  color: #15803d !important;
  -webkit-text-fill-color: #15803d !important;
}
html body.gdrs-light-preview .st-key-rd_dev_metric_neg [data-testid="stMetricValue"],
html body.gdrs-light-preview .st-key-rd_dev_metric_neg [data-testid="stMetricValue"] *,
html body.gdrs-light-preview .st-key-rd_dev_metric_neg [data-testid="metric-container"] [data-testid="stMetricValue"] {
  color: #b91c1c !important;
  -webkit-text-fill-color: #b91c1c !important;
}
html body.gdrs-light-preview .st-key-rd_dev_metric_zero [data-testid="stMetricValue"],
html body.gdrs-light-preview .st-key-rd_dev_metric_zero [data-testid="stMetricValue"] *,
html body.gdrs-light-preview .st-key-rd_dev_metric_zero [data-testid="metric-container"] [data-testid="stMetricValue"] {
  color: #6b7280 !important;
  -webkit-text-fill-color: #6b7280 !important;
}
/* KPI отклонения ПД (факт − план): ≥0 зелёный, <0 красный */
html body.gdrs-light-preview .st-key-pd_dev_metric_pos [data-testid="stMetricValue"],
html body.gdrs-light-preview .st-key-pd_dev_metric_pos [data-testid="stMetricValue"] *,
html body.gdrs-light-preview .st-key-pd_dev_metric_pos [data-testid="metric-container"] [data-testid="stMetricValue"] {
  color: #15803d !important;
  -webkit-text-fill-color: #15803d !important;
}
html body.gdrs-light-preview .st-key-pd_dev_metric_neg [data-testid="stMetricValue"],
html body.gdrs-light-preview .st-key-pd_dev_metric_neg [data-testid="stMetricValue"] *,
html body.gdrs-light-preview .st-key-pd_dev_metric_neg [data-testid="metric-container"] [data-testid="stMetricValue"] {
  color: #b91c1c !important;
  -webkit-text-fill-color: #b91c1c !important;
}
html body.gdrs-light-preview [data-testid="stForm"] [data-testid="stWidgetLabel"],
html body.gdrs-light-preview [data-testid="stForm"] [data-testid="stWidgetLabel"] p,
html body.gdrs-light-preview [data-testid="stForm"] label[data-testid="stWidgetLabel"] {
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
}
html body.gdrs-light-preview [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"],
html body.gdrs-light-preview [data-testid="stForm"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"],
html body.gdrs-light-preview section.main [data-testid="stButton"] button[data-testid^="stBaseButton-primary"],
html body.gdrs-light-preview section.main .stButton > button[kind="primary"],
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stButton"] button[data-testid^="stBaseButton-primary"],
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"] {
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%) !important;
  background-color: #ecfdf5 !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border: 1.5px solid #6ee7b7 !important;
  border-left: 5px solid #16a34a !important;
  font-weight: 700 !important;
  box-shadow: 0 1px 6px rgba(22, 163, 74, 0.18) !important;
}
html body.gdrs-light-preview [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"] *,
html body.gdrs-light-preview [data-testid="stForm"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"] *,
html body.gdrs-light-preview section.main [data-testid="stButton"] button[data-testid^="stBaseButton-primary"] *,
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stButton"] button[data-testid^="stBaseButton-primary"] *,
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"] * {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  font-weight: 700 !important;
}
html body.gdrs-light-preview [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"]:hover,
html body.gdrs-light-preview [data-testid="stForm"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"]:hover,
html body.gdrs-light-preview section.main [data-testid="stButton"] button[data-testid^="stBaseButton-primary"]:hover,
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stButton"] button[data-testid^="stBaseButton-primary"]:hover,
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"]:hover {
  background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%) !important;
  background-color: #d1fae5 !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border-color: #34d399 !important;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.28) !important;
}
html body.gdrs-light-preview [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-secondary"],
html body.gdrs-light-preview [data-testid="stForm"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-secondary"] {
  background-color: #ffffff !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border: 1px solid #cbd5e1 !important;
  font-weight: 600 !important;
  box-shadow: none !important;
}
html body.gdrs-light-preview [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-secondary"]:hover,
html body.gdrs-light-preview [data-testid="stForm"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-secondary"]:hover {
  background-color: #e5e7eb !important;
  border-color: #94a3b8 !important;
}
html body.gdrs-light-preview section.main [data-testid="stTabs"] button[data-baseweb="tab"],
html body.gdrs-light-preview .stTabs button[data-baseweb="tab"] {
  color: #4b5563 !important;
  -webkit-text-fill-color: #4b5563 !important;
}
html body.gdrs-light-preview section.main [data-testid="stTabs"] button[data-baseweb="tab"]:hover,
html body.gdrs-light-preview .stTabs button[data-baseweb="tab"]:hover {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview section.main [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"],
html body.gdrs-light-preview .stTabs button[data-baseweb="tab"][aria-selected="true"] {
  color: #16a34a !important;
  -webkit-text-fill-color: #16a34a !important;
}
html body.gdrs-light-preview section.main [data-testid="stTabs"] div[data-baseweb="tab-highlight"],
html body.gdrs-light-preview .stTabs div[data-baseweb="tab-highlight"] {
  background-color: #16a34a !important;
}
html body.gdrs-light-preview section.main [data-testid="stTabs"] div[data-baseweb="tab-border"],
html body.gdrs-light-preview .stTabs div[data-baseweb="tab-border"] {
  background-color: #cbd5e1 !important;
}
html body.gdrs-light-preview [data-testid="stAlert"] {
  background-color: #eff6ff !important;
  border: 1px solid #bfdbfe !important;
}
html body.gdrs-light-preview [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
html body.gdrs-light-preview [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p,
html body.gdrs-light-preview [data-testid="stAlert"] [data-testid="stMarkdownContainer"] * {
  color: #1e40af !important;
  -webkit-text-fill-color: #1e40af !important;
}
html body.gdrs-light-preview section.main [data-testid="stSubheader"],
html body.gdrs-light-preview section.main [data-testid="stSubheader"] p,
html body.gdrs-light-preview section.main h3 {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview section.main [data-testid="stExpander"] summary,
html body.gdrs-light-preview section.main [data-testid="stExpander"] summary p,
html body.gdrs-light-preview section.main [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"],
html body.gdrs-light-preview section.main [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] p {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body.gdrs-light-preview section.main [data-testid="stForm"] {
  background-color: #ffffff !important;
  border: 1px solid #e5e7eb !important;
  border-radius: 0.5rem !important;
  padding: 1rem 1.25rem !important;
}
html body.gdrs-light-preview section.main [data-testid="stForm"] h3,
html body.gdrs-light-preview section.main [data-testid="stForm"] [data-testid="stMarkdownContainer"] p {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def inject_light_preview_css(st) -> None:
    """CSS оболочки Streamlit для светлых превью (sidebar, фильтры, заголовки)."""
    from dashboards.gdrs_theme import inject_gdrs_light_preview_css

    inject_gdrs_light_preview_css(st)
    inject_light_filters_css(st)


def light_preview_heading_html(title: str) -> str:
    """H1 для светлого превью (чёрный заголовок, как у ГДРС)."""
    import html as _html

    safe = _html.escape(str(title or "").strip())
    return (
        f'<h1 class="main-header gdrs-light-heading bi-light-preview-heading" '
        f'style="color:#000000!important;-webkit-text-fill-color:#000000!important;'
        f'font-weight:800!important;opacity:1!important;">{safe}</h1>'
    )


def login_page_heading_html(
    *,
    subtitle: str = "Войдите в систему для доступа к панели аналитики",
    show_emoji: bool = True,
    compact: bool = False,
) -> str:
    import html as _html

    light = is_light_preview_active()
    if light:
        title = "BI Analytics"
        title_color = "#111827"
        subtitle_color = "#374151"
    else:
        title = "BI Analytics"
        title_color = "#ffffff"
        subtitle_color = "#c8d8ec"
    safe_title = _html.escape(title)
    safe_sub = _html.escape(str(subtitle or "").strip())
    emoji_block = (
        f'<h1 style="color: {title_color}; font-size: 3rem; margin-bottom: 0.5rem;">🔐</h1>'
        if show_emoji
        else ""
    )
    title_size = "1.75rem" if compact else "2rem"
    sub_block = (
        f'<p style="color: {subtitle_color}; font-size: 1.1rem;">{safe_sub}</p>'
        if safe_sub
        else ""
    )
    return (
        f'<div style="text-align: center; margin-bottom: 2rem;">'
        f"{emoji_block}"
        f'<h1 style="color: {title_color}; font-size: {title_size}; margin-bottom: 0.5rem;">'
        f"{safe_title}</h1>"
        f"{sub_block}"
        f"</div>"
    )


def render_login_light_preview_dev_toggle(st, *, key_prefix: str = "login") -> None:
    if not light_preview_reports_enabled():
        return
    st.markdown("---")
    _light_label = preview_light_name(LOGIN_PAGE_LABEL)
    _on = is_login_light_preview_active()
    c1, c2 = st.columns(2)
    with c1:
        if _on:
            if st.button("Тёмная версия", key=f"{key_prefix}_toggle_dark", width="stretch"):
                st.session_state[LOGIN_LIGHT_PREVIEW_SESSION_KEY] = False
                st.rerun()
        else:
            st.button(LOGIN_PAGE_LABEL, key=f"{key_prefix}_dark_active", disabled=True, width="stretch")
    with c2:
        if _on:
            st.button(_light_label, key=f"{key_prefix}_light_active", disabled=True, width="stretch")
        elif st.button(_light_label, key=f"{key_prefix}_toggle_light", width="stretch"):
            st.session_state[LOGIN_LIGHT_PREVIEW_SESSION_KEY] = True
            st.session_state.pop(PROFILE_LIGHT_PREVIEW_SESSION_KEY, None)
            st.session_state.pop(ADMIN_LIGHT_PREVIEW_SESSION_KEY, None)
            st.rerun()


def resolve_light_preview_title(report_name: str) -> str:
    """Заголовок H1: для ГДРС — коротко «ГДРС», иначе полное имя без суффикса превью."""
    n = str(report_name or "").strip()
    if not is_light_preview_report(n):
        return n
    nl = n.casefold()
    if nl.startswith("гдрс"):
        return "ГДРС"
    suffix = LIGHT_PREVIEW_SUFFIX
    if nl.endswith(suffix.casefold()):
        return n[: -len(suffix)].strip() or n
    return n
