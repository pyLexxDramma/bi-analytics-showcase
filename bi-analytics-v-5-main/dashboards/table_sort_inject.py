"""Интерактивная сортировка HTML-таблиц (клик по заголовку, стрелки в подписи)."""

from __future__ import annotations

import os

from utils import BI_TABLE_LAYOUT_CSS

import re

import streamlit as st
import streamlit.components.v1 as components

_TABLE_SORT_JS = r"""
(function () {
  function parseNum(t) {
    var s = String(t || "").replace(/\s/g, "").replace(/\u00a0/g, "");
    var m = s.match(/[+-]?\d+[.,]?\d*/);
    if (!m) return NaN;
    return parseFloat(m[0].replace(",", "."));
  }

  function isEmptySortVal(v) {
    return v === null || v === undefined || String(v).trim() === "";
  }

  function rowKind(tr) {
    if (!tr) return "data";
    if (tr.classList.contains("bd-total-row") || tr.classList.contains("gdrs-rk-grand") || tr.classList.contains("gdrs-rk-total") || tr.classList.contains("rk-total")) return "total";
    if (tr.classList.contains("bd-group-row") || tr.classList.contains("gdrs-rk-subtotal") || tr.classList.contains("gdrs-rk-project") || tr.classList.contains("rk-project")) return "group";
    return "data";
  }

  function cellSortKey(tr, colIdx) {
    if (!tr || !tr.cells || !tr.cells[colIdx]) return "";
    var cell = tr.cells[colIdx];
    var dv = cell.getAttribute("data-sort-val");
    if (dv !== null && dv !== "") return dv;
    return (cell.textContent || "").trim();
  }

  function compareCells(at, bt, sortDir) {
    var aEmpty = isEmptySortVal(at);
    var bEmpty = isEmptySortVal(bt);
    if (aEmpty && bEmpty) return 0;
    if (aEmpty) return 1;
    if (bEmpty) return -1;
    var an = parseNum(at), bn = parseNum(bt);
    var cmp = 0;
    if (!isNaN(an) && !isNaN(bn)) cmp = an - bn;
    else cmp = String(at).localeCompare(String(bt), "ru", { numeric: true, sensitivity: "base" });
    return sortDir > 0 ? cmp : -cmp;
  }

  function splitGroupedRows(rows) {
    var blocks = [];
    var totals = [];
    var cur = null;
    rows.forEach(function (r) {
      var k = rowKind(r);
      if (k === "total") { totals.push(r); return; }
      if (k === "group") {
        if (cur) blocks.push(cur);
        cur = { header: r, body: [] };
        return;
      }
      if (!cur) cur = { header: null, body: [] };
      cur.body.push(r);
    });
    if (cur) blocks.push(cur);
    return { blocks: blocks, totals: totals };
  }

  function tableHasProjectBlocks(rows) {
    return rows.some(function (r) {
      return (r.classList.contains("bd-group-row") || r.classList.contains("gdrs-rk-subtotal") || r.classList.contains("gdrs-rk-project") || r.classList.contains("rk-project"))
        && !r.classList.contains("bd-total-row") && !r.classList.contains("gdrs-rk-grand");
    });
  }

  function isProjectColumn(tbl, th, colIdx) {
    var label = (th && th.getAttribute("data-sort-label")) ? th.getAttribute("data-sort-label").trim().toLowerCase() : "";
    var t = label || ((th && th.textContent) ? th.textContent.trim().toLowerCase() : "");
    if (t.indexOf("проект") >= 0) return true;
    if (tbl && tbl.classList.contains("gdrs-matrix-table")) return false;
    return colIdx === 0;
  }

  function sortArrow(sortDir) {
    if (sortDir === -1) return " \u25BC";
    if (sortDir === 1) return " \u25B2";
    return " \u21C5";
  }

  function initTable(tbl) {
    if (!tbl || tbl.getAttribute("data-bi-sort-ready") === "1") return;
    tbl.setAttribute("data-bi-sort-ready", "1");
    if (!tbl.classList.contains("bi-sortable-table")) tbl.classList.add("bi-sortable-table");
    var theadRow = tbl.querySelector("thead tr");
    var gdrsWeekRow = null;
    if (tbl.classList.contains("gdrs-matrix-table")) {
      var metricsRow = tbl.querySelector("thead tr.gdrs-h-metrics");
      if (metricsRow) theadRow = metricsRow;
      var maybeWeek = metricsRow && metricsRow.nextElementSibling;
      if (maybeWeek && maybeWeek.querySelector("th.gdrs-h-week")) gdrsWeekRow = maybeWeek;
    } else if (tbl.querySelector("thead tr.title-row")) {
      var headerRows = tbl.querySelectorAll("thead tr");
      if (headerRows.length > 1) theadRow = headerRows[headerRows.length - 1];
    }
    if (!theadRow) return;
    bindSortableThs(tbl, theadRow);
    if (gdrsWeekRow) bindSortableThs(tbl, gdrsWeekRow);
  }

  function bindSortableThs(tbl, theadRow) {
    var ths = theadRow.querySelectorAll("th");
    ths.forEach(function (th, colIdx) {
      if (th.getAttribute("data-bi-sort-th") === "1") return;
      if (th.classList && th.classList.contains("blank")) return;
      if (tbl.classList.contains("gdrs-matrix-table") && th.getAttribute("data-gdrs-sort") !== "1") return;
      colIdx = th.cellIndex;
      th.setAttribute("data-bi-sort-th", "1");
      var labelText = th.getAttribute("data-sort-label") || (th.textContent || "").trim();
      labelText = labelText.replace(/\s[\u21C5\u25B2\u25BC\u2191\u2193]+$/, "").trim();
      th.innerHTML = "";
      th.style.verticalAlign = "middle";
      th.style.cursor = "pointer";
      var wrap = document.createElement("div");
      wrap.style.cssText =
        "display:flex;align-items:center;gap:6px;justify-content:flex-start;width:100%;";
      var label = document.createElement("span");
      label.className = "bi-sort-label";
      label.style.cssText =
        "flex:1;min-width:0;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;overflow:visible;text-overflow:clip;cursor:pointer;user-select:none;";
      label.title = "Клик — сортировка по убыванию, повторный клик — по возрастанию";
      wrap.appendChild(label);
      th.appendChild(wrap);
      th._biSortDir = 0;

      function resetPeerSortLabels(activeTh) {
        theadRow.querySelectorAll("th[data-bi-sort-th='1']").forEach(function (oth) {
          if (oth === activeTh) return;
          oth._biSortDir = 0;
          var lbl = oth.querySelector(".bi-sort-label");
          if (!lbl) return;
          var lt = (oth.getAttribute("data-sort-label") || "").trim();
          lt = lt.replace(/\s[\u21C5\u25B2\u25BC\u2191\u2193]+$/, "").trim();
          lbl.textContent = lt + sortArrow(0);
        });
      }

      function paintLabel() {
        label.textContent = labelText + sortArrow(th._biSortDir || 0);
      }

      function apply() {
        var tbody = tbl.querySelector("tbody");
        if (!tbody) return;
        var sortDir = th._biSortDir || 0;
        var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
        var grouped = tableHasProjectBlocks(rows);
        var byProject = isProjectColumn(tbl, th, colIdx);

        if (grouped) {
          var split = splitGroupedRows(rows);
          var ordered = [];
          if (sortDir !== 0) {
            if (byProject) {
              split.blocks.forEach(function (blk) {
                if (blk.header) blk.header.style.display = "";
              });
              split.blocks.sort(function (a, b) {
                var at = cellSortKey(a.header, colIdx) || cellSortKey(a.body[0], colIdx);
                var bt = cellSortKey(b.header, colIdx) || cellSortKey(b.body[0], colIdx);
                return compareCells(at, bt, sortDir);
              });
              split.blocks.forEach(function (blk) {
                if (blk.header) ordered.push(blk.header);
                blk.body.forEach(function (r) { ordered.push(r); });
              });
            } else {
              var allBody = [];
              split.blocks.forEach(function (blk) {
                var projLabel = "";
                if (blk.header && blk.header.cells && blk.header.cells.length) {
                  projLabel = (blk.header.cells[0].textContent || "").trim();
                }
                if (blk.header) blk.header.style.display = "none";
                blk.body.forEach(function (r) {
                  if (projLabel && r.cells && r.cells.length) {
                    var pc = r.cells[0];
                    var pt = (pc.textContent || "").trim();
                    if (!pt && pc) {
                      pc.textContent = projLabel;
                      pc.setAttribute("data-sort-val", projLabel);
                    }
                  }
                  allBody.push(r);
                });
              });
              allBody.sort(function (a, b) {
                return compareCells(cellSortKey(a, colIdx), cellSortKey(b, colIdx), sortDir);
              });
              allBody.forEach(function (r) { ordered.push(r); });
            }
          } else {
            split.blocks.forEach(function (blk) {
              if (blk.header) blk.header.style.display = "";
              if (blk.header) ordered.push(blk.header);
              blk.body.forEach(function (r) { ordered.push(r); });
            });
          }
          split.totals.forEach(function (r) { ordered.push(r); });
          ordered.forEach(function (r) {
            r.style.display = "";
            tbody.appendChild(r);
          });
          paintLabel();
          return;
        }

        if (sortDir !== 0) {
          var totals = [];
          var dataRows = [];
          var groupRows = [];
          rows.forEach(function (r) {
            var k = rowKind(r);
            if (k === "total") totals.push(r);
            else if (k === "group") groupRows.push(r);
            else dataRows.push(r);
          });
          groupRows.forEach(function (r) { r.style.display = "none"; });
          dataRows.sort(function (a, b) {
            return compareCells(cellSortKey(a, colIdx), cellSortKey(b, colIdx), sortDir);
          });
          dataRows.forEach(function (r) {
            r.style.display = "";
            tbody.appendChild(r);
          });
          totals.forEach(function (r) {
            r.style.display = "";
            tbody.appendChild(r);
          });
          paintLabel();
          return;
        }
        rows.forEach(function (r) {
          r.style.display = "";
          tbody.appendChild(r);
        });
        paintLabel();
      }

      function toggleSort(ev) {
        if (ev) {
          ev.preventDefault();
          ev.stopPropagation();
        }
        if (!th._biSortDir) {
          resetPeerSortLabels(th);
          th._biSortDir = -1;
        } else {
          th._biSortDir = th._biSortDir >= 0 ? -1 : 1;
        }
        apply();
        reportFrameHeight();
      }

      paintLabel();
      th.addEventListener("click", toggleSort);
    });
  }

  function scan(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("table.bi-sortable-table").forEach(initTable);
  }

  function __ganttFrameHeight(box) {
    if (!box) return 0;
    var tbl = box.querySelector("table");
    var content = tbl ? Math.ceil(tbl.getBoundingClientRect().height)
                      : Math.ceil(box.scrollHeight || 0);
    var cap = 600, pad = 24;
    try {
      if (content > cap) {
        box.style.setProperty("max-height", cap + "px", "important");
      } else {
        box.style.removeProperty("max-height");
      }
    } catch (e) {}
    return content > cap ? (cap + pad) : Math.max(160, content + pad);
  }

  var _rfhScheduled = false;
  function reportFrameHeight() {
    if (_rfhScheduled) return;
    _rfhScheduled = true;
    try {
      requestAnimationFrame(function () {
        _rfhScheduled = false;
        __reportFrameHeightNow();
      });
    } catch (e) {
      _rfhScheduled = false;
      __reportFrameHeightNow();
    }
  }

  function __reportFrameHeightNow() {
    try {
      // «График проекта»: высота iframe задаётся с Python (scrolling=False) —
      // postMessage/setFrameHeight + ResizeObserver давали петлю → зависание вкладки.
      if (document.querySelector(".gantt-schedule-scroll-wrap")) {
        return;
      }
      var pfScrollBox = document.querySelector(".pf-dates-scroll-wrap");
      if (pfScrollBox) {
        var pfTbl = pfScrollBox.querySelector("table");
        var content = pfTbl ? Math.ceil(pfTbl.getBoundingClientRect().height)
                            : Math.ceil(pfScrollBox.scrollHeight || 0);
        var psh = Math.min(640, content + 16);
        if (psh > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: psh }, "*");
          return;
        }
      }
      var pdScrollBox = document.querySelector(".pd-dynamics-scroll-wrap");
      if (pdScrollBox) {
        var pdTbl0 = pdScrollBox.querySelector("table");
        var pdContent = pdTbl0 ? Math.ceil(pdTbl0.getBoundingClientRect().height)
                               : Math.ceil(pdScrollBox.scrollHeight || 0);
        var pdAttr = pdScrollBox.getAttribute("data-pd-box-h");
        var pdBoxH = pdAttr ? parseInt(pdAttr, 10) : 520;
        if (!pdBoxH || pdBoxH < 120) pdBoxH = 520;
        window.parent.postMessage({ type: "streamlit:setFrameHeight", height: pdBoxH }, "*");
        return;
      }
      var fcBox = document.querySelector(".fc-table-scroll-wrap")
        || document.querySelector(".pred-detail-wrap");
      if (fcBox) {
        var fcTbl0 = fcBox.querySelector("table");
        var fcContent = fcTbl0 ? Math.ceil(fcTbl0.getBoundingClientRect().height)
                               : Math.ceil(fcBox.scrollHeight || 0);
        var fcCap = 560;
        var fcPad = 24;
        var fcH = fcContent > fcCap ? (fcCap + fcPad) : Math.max(160, fcContent + fcPad);
        if (fcH > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: fcH }, "*");
          return;
        }
      }
      var btsBox = document.querySelector(".budget-table-scroll");
      if (btsBox) {
        var btsH = Math.ceil(btsBox.getBoundingClientRect().height) + 8;
        if (btsH > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: btsH }, "*");
          return;
        }
      }
      var root = document.querySelector(".pf-covenant-table-wrap")
        || document.querySelector(".pf-dates-table-wrap")
        || document.querySelector(".pred-detail-wrap")
        || document.querySelector(".fc-table-scroll-wrap")
        || document.querySelector(".gantt-schedule-table-wrap")
        || document.querySelector(".budget-deviation-table-wrap")
        || document.querySelector(".bi-sortable-html-root")
        || document.body;
      var compact = root && (
        root.classList.contains("pf-covenant-table-wrap")
        || root.classList.contains("pf-dates-table-wrap")
        || root.classList.contains("pred-detail-wrap")
        || root.classList.contains("fc-table-scroll-wrap")
        || root.classList.contains("gantt-schedule-table-wrap")
      );
      var h = 0;
      if (root && root.getBoundingClientRect) {
        var r = root.getBoundingClientRect();
        var bottom = r.bottom + (window.scrollY || 0);
        if (compact) {
          if (root.classList.contains("pred-detail-wrap") || root.classList.contains("fc-table-scroll-wrap")) {
            h = Math.ceil(r.height) + 10;
          } else {
            // высота обёртки таблицы включает горизонтальный скроллбар → без пустоты
            h = Math.ceil(r.height) + 4;
          }
        } else {
          var el = document.documentElement;
          h = Math.ceil(Math.max(
            bottom,
            el.scrollHeight || 0,
            (document.body && document.body.scrollHeight) || 0
          )) + 14;
        }
      }
      if (h > 0) {
        window.parent.postMessage({ type: "streamlit:setFrameHeight", height: h }, "*");
      }
    } catch (e) {}
  }

  function bootDoc(doc) {
    if (!doc || !doc.body) return;
    scan(doc.body);
    reportFrameHeight();
    [0, 30, 120, 400, 1000].forEach(function (ms) {
      setTimeout(function () {
        scan(doc.body);
        reportFrameHeight();
      }, ms);
    });
  }

  bootDoc(document);
  try {
    if (!document.querySelector(".gantt-schedule-scroll-wrap")) {
      var ro = new ResizeObserver(function () { reportFrameHeight(); });
      var tgt = document.querySelector(".pd-dynamics-scroll-wrap")
        || document.querySelector(".pf-covenant-table-wrap")
        || document.querySelector(".pf-dates-table-wrap")
        || document.querySelector(".pred-detail-wrap")
        || document.querySelector(".fc-table-scroll-wrap")
        || document.querySelector(".gantt-schedule-table-wrap")
        || document.querySelector(".budget-deviation-table-wrap")
        || document.querySelector(".bi-sortable-html-root")
        || document.body;
      if (tgt) ro.observe(tgt);
    }
  } catch (e) {}
})();
"""

_TABLE_SORT_SCRIPT = f"<script>{_TABLE_SORT_JS}</script>"

# Прокрутка страницы «застревает», когда курсор над iframe-таблицей с внутренним
# вертикальным скроллом (pd-dynamics-scroll-wrap и т.п.): колесо мыши перехватывает
# внутренний контейнер и НЕ пробрасывается родительской странице (iframe не делает
# scroll-chaining к родителю). Этот скрипт вручную прокручивает основную область
# Streamlit, когда внутренний контейнер достиг границы (или прокручивать нечего).
_WHEEL_FORWARD_JS = r"""
(function () {
  function resolveParentScroller() {
    var win = window.parent || window;
    var d;
    try { d = win.document; } catch (e) { return null; }
    if (!d) return null;
    var cands = [
      d.querySelector('section.main'),
      d.querySelector('[data-testid="stMain"]'),
      d.querySelector('[data-testid="stAppViewContainer"] > section'),
      d.scrollingElement,
      d.documentElement,
      d.body
    ];
    for (var i = 0; i < cands.length; i++) {
      var c = cands[i];
      if (c && c.scrollHeight > c.clientHeight + 1) return c;
    }
    return null;
  }

  function innerScrollable(el) {
    while (el && el !== document.body && el !== document.documentElement) {
      try {
        var cs = getComputedStyle(el);
        var oy = cs.overflowY;
        if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 1) {
          return el;
        }
      } catch (e) {}
      el = el.parentElement;
    }
    return null;
  }

  function onWheel(e) {
    var dy = e.deltaY;
    if (!dy) return;
    var sc = innerScrollable(e.target);
    var atEdge;
    if (sc) {
      var atTop = sc.scrollTop <= 0;
      var atBottom = sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 1;
      atEdge = (dy < 0 && atTop) || (dy > 0 && atBottom);
    } else {
      // под курсором нет вертикального скролла — колесо должно листать страницу
      atEdge = true;
    }
    if (!atEdge) return;
    var ps = resolveParentScroller();
    if (ps) {
      ps.scrollTop += dy;
      // гасим только когда реально передали прокрутку родителю
      if (e.cancelable) e.preventDefault();
    }
  }

  try {
    window.addEventListener('wheel', onWheel, { passive: false });
  } catch (e) {
    try { window.addEventListener('wheel', onWheel); } catch (e2) {}
  }
})();
"""

_WHEEL_FORWARD_SCRIPT = f"<script>{_WHEEL_FORWARD_JS}</script>"

_COMPACT_FRAME_FIT_JS = r"""
(function () {
  function __ganttFrameHeight(box) {
    if (!box) return 0;
    var tbl = box.querySelector("table");
    var content = tbl ? Math.ceil(tbl.getBoundingClientRect().height)
                      : Math.ceil(box.scrollHeight || 0);
    var cap = 600, pad = 24;
    try {
      if (content > cap) {
        box.style.setProperty("max-height", cap + "px", "important");
      } else {
        box.style.removeProperty("max-height");
      }
    } catch (e) {}
    return content > cap ? (cap + pad) : Math.max(160, content + pad);
  }
  function fit() {
    try {
      // «График проекта»: iframe с фиксированной высотой (Python, scrolling=False).
      if (document.querySelector(".gantt-schedule-scroll-wrap")) {
        return;
      }
      var pdScroll = document.querySelector(".pd-dynamics-scroll-wrap");
      if (pdScroll) {
        try {
          var fePd = window.frameElement;
          if (fePd) {
            fePd.style.setProperty("width", "100%", "important");
            fePd.style.setProperty("max-width", "100%", "important");
            fePd.style.setProperty("display", "block", "important");
          }
        } catch (e) {}
        pdScroll.style.setProperty("width", "100%", "important");
        pdScroll.style.setProperty("min-height", "520px", "important");
        pdScroll.style.setProperty("height", "100%", "important");
        pdScroll.style.setProperty("box-sizing", "border-box", "important");
        var pdTbl = pdScroll.querySelector("table");
        if (pdTbl) {
          pdTbl.style.setProperty("width", "100%", "important");
          pdTbl.style.setProperty("min-width", "100%", "important");
          pdTbl.style.setProperty("table-layout", "fixed", "important");
        }
        var pdRoot = document.querySelector(".bi-sortable-html-root");
        if (pdRoot) {
          pdRoot.style.setProperty("width", "100%", "important");
          pdRoot.style.setProperty("height", "100%", "important");
        }
        var pdContent = pdTbl ? Math.ceil(pdTbl.getBoundingClientRect().height)
                              : Math.ceil(pdScroll.scrollHeight || 0);
        var pdAttr2 = pdScroll.getAttribute("data-pd-box-h");
        var pdBoxH2 = pdAttr2 ? parseInt(pdAttr2, 10) : 520;
        if (!pdBoxH2 || pdBoxH2 < 120) pdBoxH2 = 520;
        window.parent.postMessage({ type: "streamlit:setFrameHeight", height: pdBoxH2 }, "*");
        return;
      }
      var pdWrap = document.querySelector(".pd-dynamics-table-wrap");
      if (pdWrap) {
        try {
          var fe = window.frameElement;
          if (fe) {
            fe.style.setProperty("width", "100%", "important");
            fe.style.setProperty("max-width", "100%", "important");
            fe.style.setProperty("display", "block", "important");
          }
        } catch (e) {}
        var tbl = pdWrap.querySelector("table");
        if (tbl) {
          tbl.style.setProperty("width", "100%", "important");
          tbl.style.setProperty("min-width", "100%", "important");
          tbl.style.setProperty("table-layout", "fixed", "important");
        }
        var root = document.querySelector(".bi-sortable-html-root");
        if (root) {
          root.style.setProperty("width", "100%", "important");
          root.style.setProperty("max-width", "100%", "important");
        }
      }

      var ganttScroll = document.querySelector(".gantt-schedule-scroll-wrap");
      if (ganttScroll) {
        var gh = __ganttFrameHeight(ganttScroll);
        if (gh > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: gh }, "*");
          return;
        }
      }
      var pfScroll = document.querySelector(".pf-dates-scroll-wrap");
      if (pfScroll) {
        var pfsTbl = pfScroll.querySelector("table");
        var pcontent = pfsTbl ? Math.ceil(pfsTbl.getBoundingClientRect().height)
                              : Math.ceil(pfScroll.scrollHeight || 0);
        var ph = Math.min(640, pcontent + 16);
        if (ph > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: ph }, "*");
          return;
        }
      }
      var fc = document.querySelector(".fc-table-scroll-wrap")
        || document.querySelector(".pred-detail-wrap");
      if (fc) {
        var fcTbl = fc.querySelector("table");
        var fcContent = fcTbl ? Math.ceil(fcTbl.getBoundingClientRect().height)
                              : Math.ceil(fc.scrollHeight || 0);
        var fcCap = 560;
        var fcPad = 24;
        var fh = fcContent > fcCap ? (fcCap + fcPad) : Math.max(160, fcContent + fcPad);
        if (fh > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: fh }, "*");
          return;
        }
      }
      var bts = document.querySelector(".budget-table-scroll");
      if (bts) {
        var bsh = Math.ceil(bts.getBoundingClientRect().height) + 8;
        if (bsh > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: bsh }, "*");
          return;
        }
      }
      var root = document.querySelector(".budget-deviation-table-wrap")
        || document.querySelector(".pf-covenant-table-wrap")
        || document.querySelector(".pf-dates-table-wrap")
        || document.querySelector(".pred-detail-wrap")
        || document.querySelector(".gantt-schedule-table-wrap")
        || document.querySelector(".bi-sortable-html-root")
        || document.body;
      var pad = (root && root.classList && (root.classList.contains("pred-detail-wrap") || root.classList.contains("fc-table-scroll-wrap"))) ? 20 : 4;
      var h = 0;
      var cap = root.querySelector && root.querySelector(".budget-table-scroll");
      if (cap) {
        // бюджетная таблица с внутренним скроллом — по нижней границе скролл-области
        var cb = cap.getBoundingClientRect();
        h = Math.ceil(cb.bottom + (window.scrollY || 0)) + pad;
      } else {
        // высота обёртки таблицы (включая горизонтальный скроллбар) → кнопка вплотную
        var box2 = root.getBoundingClientRect();
        h = Math.ceil(box2.bottom + (window.scrollY || 0)) + pad;
      }
      if (h > 0) {
        window.parent.postMessage({ type: "streamlit:setFrameHeight", height: h }, "*");
      }
    } catch (e) {}
  }
  fit();
  window.addEventListener("load", fit);
  window.addEventListener("resize", function () { setTimeout(fit, 80); });
  [0, 40, 120, 300, 800, 1200, 1800].forEach(function (ms) { setTimeout(fit, ms); });
})();
"""

_IFRAME_SHELL_CSS = ("""
<style>
html, body {
  margin: 0; padding: 0;
  background: transparent;
  color: #e0e0e0;
  font-family: Inter, system-ui, sans-serif;
}

.gantt-schedule-scroll-wrap{
  display:block;width:100%!important;max-width:100%!important;margin:0;padding:0;
  overflow-x:auto!important;overflow-y:auto!important;
  -webkit-overflow-scrolling:touch;box-sizing:border-box;
  scrollbar-gutter:stable;scrollbar-width:thin;
}
.gantt-schedule-scroll-wrap thead th{position:sticky!important;top:0!important;z-index:4!important;}
.pf-dates-table-wrap,.gantt-schedule-table-wrap{
  display:block;width:100%;max-width:100%;margin:0;padding:0;
  overflow-x:visible!important;overflow-y:visible;
  -webkit-overflow-scrolling:touch;scrollbar-gutter:stable;
}
.pf-dates-scroll-wrap{
  display:block;width:100%!important;max-width:100%!important;margin:0;padding:0;
  max-height:100vh!important;height:100vh!important;overflow-x:auto!important;overflow-y:auto!important;
  -webkit-overflow-scrolling:touch;scrollbar-gutter:stable;box-sizing:border-box;
}
.pf-dates-scroll-wrap .pf-dates-table thead th{position:sticky!important;top:0!important;z-index:4!important;}
html:has(.pf-dates-scroll-wrap),body:has(.pf-dates-scroll-wrap){
  overflow:hidden!important;margin:0;padding:0;height:100%!important;min-height:0!important;
}
.bi-sortable-html-root:has(.pf-dates-scroll-wrap){
  overflow:visible!important;height:100%!important;max-height:100vh!important;
}
.bi-sortable-html-root:has(.pred-detail-wrap){overflow:visible!important;overflow-x:hidden!important}
html:has(.pred-detail-wrap),body:has(.pred-detail-wrap){overflow:hidden!important;margin:0;padding:0}
.pred-detail-wrap{
  display:block;width:100%!important;margin:0;padding:0;
  height:min(70vh,520px)!important;max-height:min(70vh,520px)!important;
  overflow-x:auto!important;overflow-y:scroll!important;
  scrollbar-gutter:stable;scrollbar-width:thin;
}
.pred-detail-wrap table{width:max-content!important;min-width:100%!important;table-layout:auto!important}
.pred-detail-wrap thead th{vertical-align:middle!important;text-align:center!important}
.pred-detail-wrap thead th>div{justify-content:center!important;align-items:center!important}
.pred-detail-wrap thead th .bi-sort-label{text-align:center!important}
.pred-detail-wrap thead th.pred-col-crit,.pred-detail-wrap thead th.pred-col-crit .bi-sort-label{white-space:nowrap!important}
.bi-sortable-html-root:has(.fc-table-scroll-wrap){
  overflow:hidden!important;overflow-x:hidden!important;
  height:100%!important;max-height:100%!important;min-height:0!important;
}
html:has(.fc-table-scroll-wrap),body:has(.fc-table-scroll-wrap){
  overflow:hidden!important;margin:0;padding:0;
  height:100%!important;min-height:0!important;max-height:100%!important;
}
.fc-table-scroll-wrap{
  display:block;width:100%!important;margin:0;padding:0;
  height:100%!important;max-height:100%!important;min-height:0!important;
  overflow-x:auto!important;overflow-y:auto!important;
  -webkit-overflow-scrolling:touch;
  scrollbar-gutter:stable;scrollbar-width:thin;box-sizing:border-box;
}
.pd-dynamics-scroll-wrap{display:block!important;width:100%!important;max-width:100%!important;min-height:520px!important;height:100%!important;max-height:100%!important;overflow-y:auto!important;overflow-x:auto!important;-webkit-overflow-scrolling:touch!important;scrollbar-gutter:stable!important;scrollbar-width:thin!important;scrollbar-color:#4a5568 #1a1c23!important;border:1px solid rgba(255,255,255,0.25)!important;border-radius:10px!important;margin:0.35em 0 0 0!important;box-sizing:border-box!important;}
.pd-dynamics-scroll-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;vertical-align:middle!important;background:hsl(209,72%,6%)!important;}
.pd-dynamics-scroll-wrap .pf-dates-table,
.pd-dynamics-table-wrap .pf-dates-table,
.bi-sortable-html-root:has(.pd-dynamics-scroll-wrap) table.pf-dates-table,
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table.pf-dates-table{
  width:100%!important;min-width:100%!important;max-width:100%!important;table-layout:fixed!important;
}
.bi-sortable-html-root:has(.pd-dynamics-scroll-wrap) table.bi-sortable-table,
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table.bi-sortable-table{
  width:100%!important;min-width:100%!important;max-width:100%!important;
}
.bi-sortable-html-root:has(.pd-dynamics-scroll-wrap),
.bi-sortable-html-root:has(.pd-dynamics-table-wrap){
  width:100%!important;max-width:100%!important;display:block!important;
}
.fc-table-scroll-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;vertical-align:middle!important;text-align:center!important;background:hsl(209,72%,6%)!important}
.bi-sortable-html-root:has(.budget-table-scroll){
  overflow:hidden!important;height:100%!important;max-height:100%!important;min-height:0!important;
}
html:has(.budget-table-scroll),body:has(.budget-table-scroll){
  overflow:hidden!important;margin:0;padding:0;height:100%!important;min-height:0!important;
}
.budget-deviation-table-wrap{
  display:flex!important;flex-direction:column!important;height:100%!important;min-height:0!important;
  overflow:hidden!important;width:100%!important;max-width:100%!important;box-sizing:border-box;
}
.budget-deviation-table-wrap:not(:has(.budget-table-scroll)){
  display:block!important;height:auto!important;max-width:100%!important;
  overflow-x:auto!important;overflow-y:visible!important;
  -webkit-overflow-scrolling:touch!important;scrollbar-gutter:stable;
}
.budget-deviation-table-wrap:not(:has(.budget-table-scroll)) table{
  width:max-content!important;min-width:100%!important;table-layout:auto!important;
}
@media (max-width:1100px){
  .budget-deviation-table-wrap:not(:has(.budget-table-scroll)){
    overflow-y:auto!important;max-height:min(70vh,640px)!important;
  }
  .budget-deviation-table-wrap:not(:has(.budget-table-scroll)) thead th{
    position:sticky!important;top:0!important;z-index:5!important;
  }
  .rendered-table-wrap,.pf-dates-table-wrap,.pf-dates-scroll-wrap,.exec-doc-table-wrap,
  .bi-styled-table-wrap,.dev-reasons-wrap,.gantt-schedule-scroll-wrap{
    overflow-x:auto!important;overflow-y:auto!important;
    max-height:min(70vh,640px)!important;-webkit-overflow-scrolling:touch!important;scrollbar-gutter:stable;
  }
  .rendered-table-wrap table,.pf-dates-table-wrap table,.exec-doc-table-wrap table,
  .bi-styled-table-wrap table,.dev-reasons-wrap table{
    width:max-content!important;min-width:100%!important;
  }
  .rendered-table-wrap thead th,.pf-dates-table-wrap thead th,.exec-doc-table-wrap thead th,
  .bi-styled-table-wrap thead th,.dev-reasons-wrap thead th,.gantt-schedule-scroll-wrap thead th{
    position:sticky!important;top:0!important;z-index:5!important;
  }
}
.budget-table-scroll{
  display:block!important;width:100%!important;height:100%!important;max-height:100%!important;
  min-height:0!important;overflow:auto!important;-webkit-overflow-scrolling:touch!important;
  scrollbar-gutter:stable;scrollbar-width:thin;box-sizing:border-box;
}
.budget-table-scroll table{width:max-content!important;min-width:100%!important;table-layout:auto!important}
.budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important}
.budget-table-scroll tr.bd-total-row td{position:sticky!important;bottom:0!important;z-index:4!important;
  box-shadow:0 -3px 10px rgba(0,0,0,0.35)!important}

.fc-table-scroll-wrap table{width:max-content!important;min-width:100%!important;table-layout:auto!important}
html,body{
  height:auto!important;min-height:0!important;
  margin:0;padding:0;width:100%;max-width:100%;
  overflow-x:hidden!important;overflow-y:visible!important;
}
.bi-sortable-html-root{
  display:block;width:100%;max-width:100%;margin:0;padding:0;
  overflow-x:auto!important;overflow-y:visible;
  -webkit-overflow-scrolling:touch;
  box-sizing:border-box;
}
.bi-sortable-html-root table.bi-sortable-table{min-width:min(100%,720px);}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table.bi-sortable-table,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table.rendered-table,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table.pf-dates-table{
  width:max-content!important;min-width:100%!important;max-width:none!important;table-layout:auto!important;
}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-id,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-id,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-lvl,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-lvl,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-pct,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-pct,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-pf-start,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-pf-start,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-pf-end,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-pf-end{
  max-width:none!important; white-space:nowrap!important;
}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-task,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-task,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-pf-project,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-pf-project,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-text,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-text{
  /* ТЗ заказчика (скрин 1): наименование задачи не обрезать — показывать полностью
     (по горизонтали таблица скроллится). */
  max-width:none!important; overflow:visible!important; text-overflow:clip!important;
  white-space:nowrap!important; text-align:left!important;
}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-reason,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-reason,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-notes,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-notes{
  min-width:10em; max-width:22em!important; white-space:normal!important;
  word-wrap:break-word!important; overflow-wrap:anywhere!important; text-align:center!important;
}
.bi-sortable-html-root:has(.pf-covenant-table-wrap) table.pf-dates-table{width:100%!important;min-width:100%!important;max-width:100%!important;}
.bi-sortable-html-root:has(.pf-dates-scroll-wrap) table.pf-dates-table{width:max-content!important;min-width:100%!important;max-width:none!important;}
.bi-sortable-html-root:has(.pf-dates-scroll-wrap) table.pf-dates-table th.col-pf-start,.bi-sortable-html-root:has(.pf-dates-scroll-wrap) table.pf-dates-table th.col-pf-end,.bi-sortable-html-root:has(.pf-dates-scroll-wrap) table.pf-dates-table th.col-pf-dur,.bi-sortable-html-root:has(.pf-dates-scroll-wrap) table.pf-dates-table td.col-pf-start,.bi-sortable-html-root:has(.pf-dates-scroll-wrap) table.pf-dates-table td.col-pf-end,.bi-sortable-html-root:has(.pf-dates-scroll-wrap) table.pf-dates-table td.col-pf-dur{white-space:nowrap!important;text-align:center!important;max-width:none!important;}
.pf-covenant-table-wrap{display:block;width:100%!important;max-width:100%!important;}
.pd-dynamics-table-wrap{display:block;width:100%!important;max-width:100%!important;box-sizing:border-box!important;margin:0!important;}
.bi-sortable-html-root:has(.pd-dynamics-table-wrap){
  width:100%!important;max-width:100%!important;display:block!important;
}
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table,
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table.bi-sortable-table,
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table.dataframe{
  width:100%!important;min-width:100%!important;max-width:100%!important;table-layout:fixed!important;
  margin:0!important;
}
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table th,
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table td{
  white-space:normal!important;word-wrap:break-word!important;overflow-wrap:anywhere!important;
}

@media (max-width:900px){
  .bi-sortable-html-root table.bi-sortable-table{min-width:640px;}
}

.bi-sortable-html-root { width: 100%; max-width: 100%; }
.bi-sortable-html-root table.bi-sortable-table {
  border-collapse: separate !important;
  border-spacing: 0 !important;
  border: 1px solid #7a9ec4 !important;
}
.bi-sortable-html-root table.bi-sortable-table th,
.bi-sortable-html-root table.bi-sortable-table td {
  border-right: 1px solid #7a9ec4 !important;
  border-bottom: 1px solid #7a9ec4 !important;
  border-top: none !important;
  border-left: none !important;
}
.bi-sortable-html-root table.bi-sortable-table thead tr:first-child th {
  border-top: 1px solid #7a9ec4 !important;
}
.bi-sortable-html-root table.bi-sortable-table tr th:first-child,
.bi-sortable-html-root table.gdrs-matrix-table thead th[data-gdrs-sort="1"],
.bi-sortable-html-root table.bi-sortable-table thead th[data-bi-sort-th="1"] {
  cursor: pointer !important;
}
.bi-sortable-html-root table.bi-sortable-table thead th .bi-sort-label {
  cursor: pointer !important;
  user-select: none;
}
</style>
"""
+ BI_TABLE_LAYOUT_CSS
+ """
<style>
.bi-sortable-html-root table.bi-sortable-table tr td:first-child {
  border-left: 1px solid #7a9ec4 !important;
}
</style>
""")

_IFRAME_SHELL_CSS_LIGHT = ("""
<style>
html, body {
  margin: 0; padding: 0;
  background: #ffffff;
  color: #111827;
  font-family: Inter, system-ui, sans-serif;
}
.bi-sortable-html-root { width: 100%; max-width: 100%; color: #111827; overflow-x: auto; -webkit-overflow-scrolling: touch; }
.bi-sortable-html-root .budget-deviation-table-wrap:not(:has(.budget-table-scroll)){
  overflow-x:auto!important;overflow-y:visible!important;max-width:100%!important;
}
@media (max-width:1100px){
  .bi-sortable-html-root .budget-deviation-table-wrap:not(:has(.budget-table-scroll)){
    overflow-y:auto!important;max-height:min(70vh,640px)!important;
  }
  .bi-sortable-html-root .budget-deviation-table-wrap:not(:has(.budget-table-scroll)) thead th{
    position:sticky!important;top:0!important;z-index:5!important;
  }
}
.bi-sortable-html-root h3.bi-table-caption,
.bi-sortable-html-root .bi-table-caption {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  opacity: 1 !important;
}
.bi-sortable-html-root table.bi-sortable-table {
  border-collapse: separate !important;
  border-spacing: 0 !important;
  border: 1px solid #cbd5e1 !important;
}
.bi-sortable-html-root table.bi-sortable-table th,
.bi-sortable-html-root table.bi-sortable-table td {
  border-right: 1px solid #cbd5e1 !important;
  border-bottom: 1px solid #cbd5e1 !important;
  border-top: none !important;
  border-left: none !important;
  color: #111827;
}
.bi-sortable-html-root table.bi-sortable-table thead tr:first-child th {
  border-top: 1px solid #cbd5e1 !important;
}
.bi-sortable-html-root table.bi-sortable-table tr th:first-child,
.bi-sortable-html-root table.bi-sortable-table tr td:first-child {
  border-left: 1px solid #cbd5e1 !important;
}
.bi-sortable-html-root .bi-sort-label { color: #111827 !important; }
.bi-sortable-html-root td.bd-cell-green,
.bi-sortable-html-root td.bd-cell-green * {
  color: hsl(148, 72%, 36%) !important;
  -webkit-text-fill-color: hsl(148, 72%, 36%) !important;
  -webkit-text-stroke: 0.28px #111827 !important;
  paint-order: stroke fill;
  text-shadow: -0.28px 0 #111827, 0.28px 0 #111827, 0 -0.28px #111827, 0 0.28px #111827 !important;
}
.bi-sortable-html-root td.bd-cell-red,
.bi-sortable-html-root td.bd-cell-red * {
  color: hsl(348, 82%, 42%) !important;
}
.bi-sortable-html-root .rendered-table th,
.bi-sortable-html-root .pf-dates-table th,
.bi-sortable-html-root .pf-dates-scroll-wrap .pf-dates-table thead th,
.bi-sortable-html-root .rendered-table thead th {
  background: #f3f4f6 !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border-bottom: 2px solid #e2e8f0 !important;
}
.bi-sortable-html-root .rendered-table th .bi-sort-label,
.bi-sortable-html-root .pf-dates-table th .bi-sort-label {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
.bi-sortable-html-root .rendered-table td,
.bi-sortable-html-root .pf-dates-table td {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border-bottom-color: #e5e7eb !important;
}
.bi-sortable-html-root .rendered-table tr:hover td {
  background-color: #f8fafc !important;
}
.bi-sortable-html-root .rendered-table tr:nth-child(even) td {
  background-color: #fafbfc !important;
}
</style>
"""
+ BI_TABLE_LAYOUT_CSS
+ """
<style>
.bi-sortable-html-root .bi-sort-filter,
.bi-sortable-html-root select.bi-sort-filter { display: none !important; }
.bi-sortable-html-root .bi-sort-filter {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #94a3b8 !important;
}
</style>
""")


_GDRS_TABLE_WRAP_IFRAME_CSS = """
<style>
html, body {
  overflow-x: hidden !important;
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}
.bi-sortable-html-root {
  width: 100% !important;
  max-width: 100% !important;
  overflow-x: hidden !important;
  box-sizing: border-box !important;
}
.gdrs-table-wrap {
  display: block !important;
  width: 100% !important;
  max-width: 100% !important;
  overflow-x: auto !important;
  overflow-y: visible !important;
  -webkit-overflow-scrolling: touch !important;
}
.gdrs-table-wrap .gdrs-matrix-table {
  width: max-content !important;
  min-width: 100% !important;
}
</style>
"""

def _iframe_shell_css(html: str) -> str:
    html_l = html or ""
    use_light = "gdrs-light-table" in html_l
    if not use_light:
        try:
            from config import is_showcase_mode

            if is_showcase_mode():
                use_light = any(
                    m in html_l
                    for m in (
                        "budget-deviation-table-wrap",
                        "pf-dates-table-wrap",
                        "pf-zos-table-wrap",
                        "pf-dates-table",
                        "rendered-table-wrap",
                    )
                )
        except Exception:
            pass
    base = _IFRAME_SHELL_CSS_LIGHT if use_light else _IFRAME_SHELL_CSS
    if "gdrs-table-wrap" in html_l:
        return base + _GDRS_TABLE_WRAP_IFRAME_CSS
    return base


def table_sort_inject_enabled() -> bool:
    return os.environ.get("BI_ANALYTICS_TABLE_SORT", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _split_embedded_style(html: str) -> tuple[str, str]:
    text = html or ""
    styles = re.findall(r"<style[^>]*>.*?</style>", text, flags=re.I | re.S)
    if styles:
        body = re.sub(r"<style[^>]*>.*?</style>", "", text, count=len(styles), flags=re.I | re.S).strip()
        return "".join(styles), body
    return "", text


def _estimate_html_block_height(html: str) -> int:
    # ВАЖНО: классы-обёртки берём из разметки без <style>, иначе CSS-определения
    # (.pf-dates-scroll-wrap{...} и т.п.) ложно срабатывают на substring-проверках.
    html_l = re.sub(r"<style[^>]*>.*?</style>", "", html or "", flags=re.I | re.S)
    m_rows = re.search(r'data-bi-rows="(\d+)"', html_l)
    if m_rows:
        data_rows = int(m_rows.group(1))
    else:
        bodies = re.findall(r"<tbody[^>]*>(.*?)</tbody>", html, re.I | re.S)
        if bodies:
            data_rows = sum(part.count("<tr") for part in bodies)
        else:
            data_rows = max(0, html.count("<tr") - 1)
    if "gdrs-summary-table-wrap" in html_l:
        thead_h = 76
        row_h = 44
        extra = 40
        cap = 1400
    elif "gdrs-matrix-table" in html_l or "gdrs-table-wrap" in html_l:
        thead_h = 132
        row_h = 38
        extra = 56
        cap = 2600
    elif "budget-deviation-table-wrap" in html_l:
        thead_h = 64
        row_h = 32
        extra = 16
        cap = 900
    elif "gantt-schedule-scroll-wrap" in html_l:
        thead_h = 44
        row_h = 28
        extra = 16
        cap = 640
    elif "pf-dates-scroll-wrap" in html_l:
        thead_h = 44
        row_h = 28
        extra = 12
        cap = 640
    elif "pd-dynamics-scroll-wrap" in html_l:
        thead_h = 42
        row_h = 27
        extra = 48
        cap = 720
    elif "pd-dynamics-table-wrap" in html_l:
        thead_h = 42
        row_h = 27
        extra = 4
    elif "pf-covenant-table-wrap" in html_l:
        thead_h = 42
        row_h = 27
        extra = 4
    elif "pf-dates-table-wrap" in html_l or "pf-dates-table" in html_l:
        thead_h = 42
        row_h = 27
        extra = 6
    elif "fc-table-scroll-wrap" in html_l:
        thead_h = 56
        row_h = 34
        extra = 48
    elif "pred-detail-wrap" in html_l:
        thead_h = 56
        row_h = 50
        extra = 48
    elif "bi-sortable-table" in html_l:
        thead_h = 68
        row_h = 34
        extra = 24
        cap = 1000
    else:
        thead_h = 44
        row_h = 27
        extra = 16
        cap = 900
    n_group = html_l.count("bd-group-row")
    n_total = html_l.count("bd-total-row")
    n_plain = max(0, data_rows - n_group - n_total)
    est = thead_h + n_plain * row_h + n_group * (row_h + 8) + n_total * (row_h + 10) + extra
    if "budget-deviation-table-wrap" in html_l:
        m_vh = re.search(r"max-height:\s*([\d.]+)vh", html_l)
        if m_vh and "budget-table-scroll" in html_l:
            vh_cap = int(max(200, min(720, float(m_vh.group(1)) * 10 + 56)))
            if data_rows <= 18:
                return int(max(120, est))
            return int(max(120, min(est, vh_cap)))
        return int(max(120, est))
    if "gantt-schedule-scroll-wrap" in html_l:
        return int(max(96, est))
    if "pf-dates-scroll-wrap" in html_l:
        return int(min(cap, max(200, est)))
    if "pd-dynamics-scroll-wrap" in html_l:
        return int(min(cap, max(520, est + 24)))
    if "pd-dynamics-table-wrap" in html_l:
        return int(max(68, est))
    if "pf-covenant-table-wrap" in html_l:
        return int(max(68, est))
    if "pf-dates-table-wrap" in html_l or "pf-dates-table" in html_l:
        return int(max(72, est))
    if "pred-detail-wrap" in html_l:
        return int(max(420, min(820, est + 24)))
    if "fc-table-scroll-wrap" in html_l:
        return int(max(840, min(1640, est + 24)))
    return int(min(cap, max(120, est)))




def _gdrs_matrix_fullscreen_shell_wrap(body: str) -> str:
    """Обёртка ГДРС-матрицы: кнопка ⛶ и полноэкранный overlay как в Девелоперских проектах."""
    from dashboards.dev_projects_tz_matrix import (
        _MATRIX_IFRAME_FIT_HEIGHT_SCRIPT,
        _MATRIX_IFRAME_FULLSCREEN_SCRIPT,
    )

    inner = body or ""
    if "matrix-fs-root" in inner:
        return inner
    return (
        '<div id="matrix-fs-root" class="matrix-fs-root">'
        '<div class="matrix-fs-topbar" role="toolbar" aria-label="Таблица">'
        '<button type="button" class="matrix-fs-btn" id="matrix-fs-btn" title="На весь экран">'
        "\u26f6</button></div>"
        '<div class="matrix-fs-body gdrs-fs-body cp-body-stack">'
        + inner
        + "</div></div>"
        + _MATRIX_IFRAME_FULLSCREEN_SCRIPT
        + (_MATRIX_IFRAME_FIT_HEIGHT_SCRIPT or "")
    )


def _gdrs_fullscreen_head_css() -> str:
    from dashboards.dev_projects_tz_matrix import _MATRIX_IFRAME_FULLSCREEN_SHELL_CSS

    return "<style>" + _MATRIX_IFRAME_FULLSCREEN_SHELL_CSS + "</style>"

def _build_sortable_html_document(html: str) -> str:
    style_block, body = _split_embedded_style(html)
    html_l = html or ""
    fs_css = ""
    if "gdrs-table-wrap" in html_l:
        body = _gdrs_matrix_fullscreen_shell_wrap(body)
        fs_css = _gdrs_fullscreen_head_css()
    return (
        "<!DOCTYPE html><html lang='ru'><head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"{style_block}{_iframe_shell_css(html)}{fs_css}"
        "</head><body>"
        f"<div class='bi-sortable-html-root'>{body}{_TABLE_SORT_SCRIPT}{_WHEEL_FORWARD_SCRIPT}"
        + (
            f"<script>{_COMPACT_FRAME_FIT_JS}</script>"
            if (
                "gantt-schedule-scroll-wrap" not in html_l
                and (
                "pf-dates-table-wrap" in html_l
                or "pf-covenant-table-wrap" in html_l
                or "pf-dates-table" in html_l
                or "gantt-schedule-table-wrap" in html_l
                or (
                    "budget-deviation-table-wrap" in html_l
                    and "budget-table-scroll" in html_l
                )
                or "pd-dynamics-table-wrap" in html_l
                or "bi-styled-table-wrap" in html_l
                or "rendered-table-wrap" in html_l
                or "dev-reasons-wrap" in html_l
                or "fc-table-scroll-wrap" in html_l
                or "pf-dates-scroll-wrap" in html_l
                )
            )
            else ""
        )
        + "</div>"
        "</body></html>"
    )


def _html_block_compact(html: str) -> bool:
    html_l = html or ""
    return (
        "pf-dates-table-wrap" in html_l
        or "pf-covenant-table-wrap" in html_l
        or "pf-dates-scroll-wrap" in html_l
        or "pf-dates-table" in html_l
        or "pred-detail-wrap" in html_l
        or "fc-table-scroll-wrap" in html_l
        or "gantt-schedule-table-wrap" in html_l
        or "gantt-schedule-scroll-wrap" in html_l
        or "rendered-table-wrap" in html_l
        or "dev-reasons-wrap" in html_l
        or "pd-dynamics-table-wrap" in html_l
        or "bi-styled-table-wrap" in html_l
        or "fc-table-scroll-wrap" in html_l
        or "budget-deviation-table-wrap" in html_l
    )


def render_sortable_html_block(html: str, *, compact_iframe: bool | None = None) -> None:
    """Таблица + JS; для plan-fact — st.html (высота по контенту), иначе components.html."""
    if not html:
        return
    if not table_sort_inject_enabled():
        st.markdown(html, unsafe_allow_html=True)
        return
    doc = _build_sortable_html_document(html)
    # Маршрутизация по реальным классам-обёрткам (без <style>): иначе CSS-селекторы
    # в _TABLE_CSS ложно матчатся подстрокой и все таблицы уходят в одну ветку.
    _b = re.sub(r"<style[^>]*>.*?</style>", "", html or "", flags=re.I | re.S)
    if "pred-detail-wrap" in _b:
        doc_sc = doc.replace("</head>", '<style>html,body{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}.bi-sortable-html-root{height:100%!important;min-height:0!important;overflow:hidden!important;}html body .fc-table-scroll-wrap,html body .pred-detail-wrap,html body .budget-table-scroll{height:100%!important;max-height:100%!important;min-height:0!important;overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;}html body .fc-table-scroll-wrap thead th,html body .pred-detail-wrap thead th,html body .budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important;background:hsl(209,72%,6%)!important;}</style>' + "</head>", 1)
        components.html(doc_sc, height=584, scrolling=False)
        return
    if "pf-dates-scroll-wrap" in _b:
        _h_scroll = min(640, max(280, _estimate_html_block_height(html)))
        components.html(doc, height=_h_scroll, scrolling=False)
        return
    if "gantt-schedule-scroll-wrap" in _b:
        # Таблица задач «График проекта»: фиксированная высота окна с внутренней
        # вертикальной прокруткой (как «Причины отклонений»/«Прогноз БДДС»).
        # Кнопка «Скачать таблицу» — сразу под таблицей, без пустого пространства.
        # Горизонтальный скролл — внутри обёртки (overflow-x:auto), шапка sticky.
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{height:100%!important;min-height:0!important;overflow:hidden!important;}'
            'html body .gantt-schedule-scroll-wrap{height:100%!important;max-height:100%!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;}'
            'html body .gantt-schedule-scroll-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;'
            'background:hsl(209,72%,6%)!important;}</style></head>',
            1,
        )
        _h_gantt = min(624, max(180, _estimate_html_block_height(html) + 24))
        components.html(doc_sc, height=_h_gantt, scrolling=False)
        return
    if "budget-deviation-table-wrap" in _b and "budget-table-scroll" in _b:
        _m_vh = re.search(r'data-scroll-vh="([\d.]+)"', html or "") or re.search(
            r"max-height:\s*([\d.]+)vh", html or ""
        )
        _vh = float(_m_vh.group(1)) if _m_vh else 52.0
        _h_b = int(min(640, max(280, _vh * 10 + 56)))
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{height:100%!important;min-height:0!important;overflow:hidden!important;}'
            'html body .budget-table-scroll{height:100%!important;max-height:100%!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;}'
            'html body .budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important;}'
            'html body .budget-table-scroll tr.bd-total-row td{position:sticky!important;bottom:0!important;z-index:4!important;}'
            '</style></head>',
            1,
        )
        components.html(doc_sc, height=_h_b, scrolling=False)
        return
    if "pd-dynamics-scroll-wrap" in _b:
        _m_pd = re.search(r'data-pd-box-h="(\d+)"', html or "")
        _h_pd = int(_m_pd.group(1)) if _m_pd else min(720, max(520, _estimate_html_block_height(html)))
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{height:100%!important;min-height:0!important;overflow:hidden!important;}'
            'html body .pd-dynamics-scroll-wrap{height:100%!important;max-height:100%!important;min-height:100%!important;'
            'width:100%!important;max-width:100%!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
            'scrollbar-gutter:stable!important;box-sizing:border-box!important;}'
            'html body .pd-dynamics-scroll-wrap .pf-dates-table,'
            'html body .pd-dynamics-table-wrap .pf-dates-table{'
            'width:100%!important;min-width:100%!important;max-width:100%!important;table-layout:fixed!important;}'
            'html body .pd-dynamics-scroll-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;'
            'background:hsl(209,72%,6%)!important;}</style></head>',
            1,
        )
        components.html(doc_sc, height=_h_pd, scrolling=False)
        return
    if "fc-table-scroll-wrap" in _b:
        doc_sc = doc.replace("</head>", '<style>html,body{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}.bi-sortable-html-root{height:100%!important;min-height:0!important;overflow:hidden!important;}html body .fc-table-scroll-wrap,html body .pred-detail-wrap,html body .budget-table-scroll{height:100%!important;max-height:100%!important;min-height:0!important;overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;}html body .fc-table-scroll-wrap thead th,html body .pred-detail-wrap thead th,html body .budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important;}</style>' + "</head>", 1)
        components.html(doc_sc, height=584, scrolling=False)
        return
    # Не st.html: <script> сортировки в основной DOM часто не выполняется (↕ видны, клик мёртвый).
    _compact = (
        _html_block_compact(html)
        if compact_iframe is None
        else bool(compact_iframe)
    )
    if _compact:
        _h_compact = _estimate_html_block_height(html)
        _covenant_tbl = "pf-covenant-table-wrap" in _b
        _pd_tbl = "pd-dynamics-table-wrap" in _b and "pd-dynamics-scroll-wrap" not in _b
        _wide_tbl = (
            "pf-dates-table-wrap" in _b
            or "pf-dates-table" in _b
            or "gantt-schedule-table-wrap" in _b
        )
        # scrolling=False: iframe ужимается по высоте контента (setFrameHeight),
        # без пустоты под таблицей. Горизонтальный скролл широкой таблицы —
        # внутри обёртки .pf-dates-table-wrap (overflow-x:auto), pad — запас на скроллбар.
        if _covenant_tbl or _pd_tbl:
            _pad_h = 2
        elif "budget-deviation-table-wrap" in (html or ""):
            _pad_h = 4
        elif _wide_tbl:
            _pad_h = 18
        else:
            _pad_h = 10
        components.html(
            doc,
            height=max(68 if (_covenant_tbl or _pd_tbl) else 96, _h_compact + _pad_h),
            scrolling=False,
        )
        return
    _h = _estimate_html_block_height(html)
    if "pred-detail-wrap" not in (html or "") and "fc-table-scroll-wrap" not in (html or "") and "gdrs-matrix-table" not in (html or ""):
        _h = min(900, max(320, int(_h)))
    _no_iframe_scroll = (
        "gdrs-summary-table-wrap",
        "budget-deviation-table-wrap",
        "pf-dates-table-wrap",
        "pred-detail-wrap",
        "fc-table-scroll-wrap",
        "gantt-schedule-table-wrap",
        "exec-doc-table-wrap",
        "rendered-table-wrap",
        "bi-styled-table-wrap",
        "dev-reasons-wrap",
        "gdrs-table-wrap",
    )
    _scroll = not any(m in (html or "") for m in _no_iframe_scroll)
    if "budget-deviation-table-wrap" in (html or ""):
        if "budget-table-scroll" not in (html or ""):
            _h = int(_h) + 12
    elif _compact:
        _scroll = False
    _h = _h + (4 if not _scroll else 0)
    components.html(doc, height=_h, scrolling=_scroll)


def inject_sortable_tables_script() -> None:
    if not table_sort_inject_enabled():
        return
    components.html(
        _build_sortable_html_document("<div></div>"),
        height=0,
        scrolling=False,
    )


def rescan_sortable_tables_after_render() -> None:
    """Legacy: таблицы рендерятся через render_sortable_html_block."""
    if not table_sort_inject_enabled():
        return
    inject_sortable_tables_script()
