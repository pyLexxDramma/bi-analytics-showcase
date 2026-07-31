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
    if (tbl.closest(".gantt-schedule-table-wrap") && tbl.hasAttribute("data-gantt-task-ch")) {
      __fitGanttTaskColumns(tbl.parentElement || document);
    }
  }

  function getThLabelText(th, tbl) {
    if (!th) return "";
    var lt = (th.getAttribute("data-sort-label") || th._biSortLabelText || "").trim();
    if (!lt && tbl && tbl._biSortLabelsByIdx && tbl._biSortLabelsByIdx[th.cellIndex]) {
      lt = String(tbl._biSortLabelsByIdx[th.cellIndex] || "").trim();
    }
    lt = lt.replace(/\s[\u21C5\u25B2\u25BC\u2191\u2193]+$/, "").trim();
    if (!lt) {
      var seedLbl = th.querySelector(".bi-sort-label");
      if (seedLbl) {
        lt = (seedLbl.textContent || "").replace(/\s[\u21C5\u25B2\u25BC\u2191\u2193]+$/, "").trim();
      }
    }
    if (!lt) {
      lt = (th.textContent || "").replace(/\s[\u21C5\u25B2\u25BC\u2191\u2193]+$/, "").trim();
    }
    if (lt) {
      th._biSortLabelText = lt;
      th.setAttribute("data-sort-label", lt);
      if (tbl) {
        if (!tbl._biSortLabelsByIdx) tbl._biSortLabelsByIdx = {};
        tbl._biSortLabelsByIdx[th.cellIndex] = lt;
      }
    }
    return lt;
  }

  function bindSortableThs(tbl, theadRow) {
    var ths = theadRow.querySelectorAll("th");
    ths.forEach(function (th, colIdx) {
      if (th.getAttribute("data-bi-sort-th") === "1") return;
      if (th.classList && th.classList.contains("blank")) return;
      if (tbl.classList.contains("gdrs-matrix-table") && th.getAttribute("data-gdrs-sort") !== "1") return;
      colIdx = th.cellIndex;
      th.setAttribute("data-bi-sort-th", "1");
      var labelText = getThLabelText(th, tbl);
      th.innerHTML = "";
      th.style.verticalAlign = "middle";
      th.style.cursor = "pointer";
      var isGanttTask = th.classList && th.classList.contains("col-gantt-task");
      var isPfDates = tbl.classList && tbl.classList.contains("pf-dates-table");
      var wrap = document.createElement("div");
      wrap.style.cssText = isGanttTask
        ? "display:flex;align-items:center;gap:4px;justify-content:flex-start;width:auto;"
        : "display:flex;align-items:center;gap:6px;justify-content:flex-start;width:100%;";
      var label = document.createElement("span");
      label.className = "bi-sort-label";
      label.style.cssText = isGanttTask
        ? "flex:0 0 auto;min-width:0;white-space:nowrap;overflow:visible;text-overflow:clip;cursor:pointer;user-select:none;"
        : (isPfDates
          ? "flex:0 0 auto;min-width:0;white-space:nowrap;overflow:visible;text-overflow:clip;cursor:pointer;user-select:none;"
          : "flex:1;min-width:0;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;overflow:visible;text-overflow:clip;cursor:pointer;user-select:none;");
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
          var lt = getThLabelText(oth, tbl);
          lbl.textContent = lt + sortArrow(0);
        });
      }

      function paintLabel() {
        var lt = labelText || getThLabelText(th, tbl);
        label.textContent = lt + sortArrow(th._biSortDir || 0);
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
        __fitGanttTaskColumns(tbl.parentElement || document);
        reportFrameHeight();
      }

      paintLabel();
      th.addEventListener("click", toggleSort);
    });
  }

  function scan(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("table.bi-sortable-table").forEach(initTable);
    __fitGanttTaskColumns(root);
  }

  function __fitGanttTaskColumns(root) {
    var scope = root && root.querySelectorAll ? root : document;
    if (!scope.querySelectorAll) return;
    scope.querySelectorAll(".gantt-schedule-table-wrap table[data-gantt-task-ch]").forEach(function (tbl) {
      var ch = tbl.getAttribute("data-gantt-task-ch");
      if (!ch) return;
      var w = ch + "ch";
      var col = tbl.querySelector("colgroup col.col-gantt-task");
      if (col) {
        col.style.setProperty("width", w, "important");
        col.style.setProperty("min-width", w, "important");
        col.style.setProperty("max-width", w, "important");
      }
      tbl.querySelectorAll("th.col-gantt-task, td.col-gantt-task").forEach(function (cell) {
        cell.style.setProperty("width", w, "important");
        cell.style.setProperty("min-width", w, "important");
        cell.style.setProperty("max-width", w, "important");
        cell.style.setProperty("white-space", "nowrap", "important");
      });
      tbl.style.setProperty("table-layout", "auto", "important");
      tbl.style.setProperty("width", "max-content", "important");
      tbl.style.setProperty("min-width", "100%", "important");
    });
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
        var pdAttr = pdScrollBox.getAttribute("data-scroll-box-h")
          || pdScrollBox.getAttribute("data-pd-box-h");
        var pdCap = pdAttr ? parseInt(pdAttr, 10) : 640;
        if (!pdCap || pdCap < 120) pdCap = 640;
        var pdBoxH = Math.min(pdCap, Math.max(120, pdContent + 16));
        pdScrollBox.style.setProperty("height", pdBoxH + "px", "important");
        pdScrollBox.style.setProperty("max-height", pdBoxH + "px", "important");
        pdScrollBox.style.setProperty("min-height", "0", "important");
        window.parent.postMessage({ type: "streamlit:setFrameHeight", height: pdBoxH }, "*");
        return;
      }
      var execBox = document.querySelector(".exec-doc-scroll-wrap");
      if (execBox) {
        try {
          var feEx = window.frameElement;
          if (feEx) {
            feEx.style.setProperty("width", "100%", "important");
            feEx.style.setProperty("max-width", "100%", "important");
            feEx.style.setProperty("display", "block", "important");
          }
        } catch (e) {}
        execBox.style.setProperty("width", "100%", "important");
        execBox.style.setProperty("max-width", "100%", "important");
        var exH = Math.ceil(execBox.getBoundingClientRect().height) + 24;
        if (exH > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: exH }, "*");
          return;
        }
      }
      var fcBox = document.querySelector(".fc-table-scroll-wrap")
        || document.querySelector(".pred-detail-wrap");
      if (fcBox) {
        try {
          var feFc0 = window.frameElement;
          if (feFc0) {
            feFc0.style.setProperty("width", "100%", "important");
            feFc0.style.setProperty("max-width", "100%", "important");
            feFc0.style.setProperty("display", "block", "important");
          }
        } catch (e) {}
        fcBox.style.setProperty("width", "100%", "important");
        fcBox.style.setProperty("max-width", "100%", "important");
        var fcTbl0 = fcBox.querySelector("table");
        if (fcTbl0) {
          var fcLight = !!(document.querySelector(".gdrs-light-table, .bi-light-table")
            || (document.body && document.body.classList.contains("gdrs-light-preview")));
          if (fcLight) {
            fcTbl0.style.setProperty("width", "max-content", "important");
            fcTbl0.style.setProperty("min-width", "100%", "important");
            fcTbl0.style.setProperty("table-layout", "auto", "important");
          } else {
            fcTbl0.style.setProperty("width", "100%", "important");
            fcTbl0.style.setProperty("min-width", "100%", "important");
            fcTbl0.style.setProperty("max-width", "100%", "important");
            fcTbl0.style.setProperty("table-layout", "fixed", "important");
          }
        }
        var fcRoot0 = document.querySelector(".bi-sortable-html-root");
        if (fcRoot0) {
          fcRoot0.style.setProperty("width", "100%", "important");
          fcRoot0.style.setProperty("max-width", "100%", "important");
        }
        var parentH = 0;
        try {
          if (window.frameElement && window.frameElement.clientHeight) {
            parentH = window.frameElement.clientHeight;
          }
        } catch (e) {}
        var vhFc = parseFloat(fcBox.getAttribute("data-scroll-vh") || "0");
        var fcH;
        if (vhFc > 0) {
          // длинная скролл-таблица (plan/fact): занять высоту вьюпорта
          if (parentH <= 120 && window.innerHeight) {
            parentH = Math.min(window.innerHeight * vhFc / 100, window.innerHeight * 0.92);
          }
          fcH = parentH > 120 ? parentH : Math.ceil(Math.max(280, vhFc * window.innerHeight / 100 + 12));
        } else {
          // self-size (обёртка height:auto + max-height): высота по контенту, а не
          // echo стартового clientHeight — иначе iframe залипает на завышенной
          // высоте и остаётся пустота перед кнопкой «Скачать таблицу».
          fcH = Math.ceil(fcBox.getBoundingClientRect().height) + 10;
        }
        if (fcH > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: fcH }, "*");
          return;
        }
      }
      var btsBox = document.querySelector(".budget-table-scroll");
      if (btsBox) {
        var boxAttr = parseInt(btsBox.getAttribute("data-scroll-box-h") || "0", 10);
        if (boxAttr > 0) {
          btsBox.style.setProperty("height", boxAttr + "px", "important");
          btsBox.style.setProperty("max-height", boxAttr + "px", "important");
          btsBox.style.setProperty("min-height", "0", "important");
          btsBox.style.setProperty("overflow-x", "auto", "important");
          btsBox.style.setProperty("overflow-y", "auto", "important");
          if (btsBox.classList.contains("pred-detail-scroll")) {
            btsBox.style.setProperty("margin", "0", "important");
            btsBox.style.setProperty("overflow-x", "scroll", "important");
            btsBox.style.setProperty("padding-bottom", "16px", "important");
            btsBox.style.setProperty("scroll-padding-bottom", "16px", "important");
          }
        }
        var parentH0 = 0;
        try {
          if (window.frameElement && window.frameElement.clientHeight) {
            parentH0 = window.frameElement.clientHeight;
          }
        } catch (e) {}
        var vhAttr = parseFloat(btsBox.getAttribute("data-scroll-vh") || "0");
        var capPx = 0;
        if (vhAttr > 0 && window.innerHeight) {
          capPx = Math.min(window.innerHeight * vhAttr / 100, window.innerHeight * 0.92);
        }
        var btsH = boxAttr > 0 ? boxAttr : (parentH0 > 120 ? parentH0
          : (capPx > 0 ? Math.ceil(Math.max(280, capPx + 12)) : 320));
        if (btsBox.classList.contains("pred-detail-scroll") && btsH > 0) {
          btsH = btsH + 16;
        }
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
        || document.querySelector(".gdrs-summary-table-wrap")
        || document.querySelector(".bi-sortable-html-root")
        || document.body;
      // Сводные таблицы без внутреннего скролла (БДДС/БДР/бюджет по проектам,
      // ГДРС-сводки, причины отклонений и т.п.): мерить фактическую высоту
      // контента, а не scrollHeight (иначе iframe не ужимается ниже завышенной
      // первичной оценки → пустота между таблицей и кнопкой «Скачать таблицу»).
      var _noInnerScroll = !document.querySelector(".budget-table-scroll");
      var compact = root && (
        root.classList.contains("pf-covenant-table-wrap")
        || root.classList.contains("pf-dates-table-wrap")
        || root.classList.contains("pred-detail-wrap")
        || root.classList.contains("fc-table-scroll-wrap")
        || root.classList.contains("gantt-schedule-table-wrap")
        || (root.classList.contains("budget-deviation-table-wrap") && _noInnerScroll)
        || root.classList.contains("gdrs-summary-table-wrap")
        || root.classList.contains("bi-sortable-html-root")
      );
      var h = 0;
      if (root && root.getBoundingClientRect) {
        var _measure = root;
        if (root.classList.contains("bi-sortable-html-root")) {
          _measure = root.querySelector(
            ".budget-deviation-table-wrap,.gdrs-summary-table-wrap,.dev-reasons-wrap,"
            + ".rendered-table-wrap,.bi-styled-table-wrap,table"
          ) || root;
        }
        var r = _measure.getBoundingClientRect();
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
  window.__fitGanttTaskColumns = __fitGanttTaskColumns;
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
          pdRoot.style.setProperty("max-width", "100%", "important");
        }
        var pdContent2 = pdTbl ? Math.ceil(pdTbl.getBoundingClientRect().height)
                               : Math.ceil(pdScroll.scrollHeight || 0);
        var pdAttr2 = pdScroll.getAttribute("data-scroll-box-h")
          || pdScroll.getAttribute("data-pd-box-h");
        var pdCap2 = pdAttr2 ? parseInt(pdAttr2, 10) : 640;
        if (!pdCap2 || pdCap2 < 120) pdCap2 = 640;
        var pdBoxH2 = Math.min(pdCap2, Math.max(120, pdContent2 + 16));
        pdScroll.style.setProperty("height", pdBoxH2 + "px", "important");
        pdScroll.style.setProperty("max-height", pdBoxH2 + "px", "important");
        pdScroll.style.setProperty("min-height", "0", "important");
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

      var gdrsSum = document.querySelector(".gdrs-summary-table-wrap");
      if (gdrsSum) {
        var gTbl = gdrsSum.querySelector("table");
        var gContent = gTbl ? Math.ceil(gTbl.getBoundingClientRect().height)
                            : Math.ceil(gdrsSum.scrollHeight || 0);
        var ghSum = Math.max(120, gContent + 24);
        if (ghSum > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: ghSum }, "*");
          return;
        }
      }
      var ganttScroll = document.querySelector(".gantt-schedule-scroll-wrap");
      if (ganttScroll) {
        if (typeof window.__fitGanttTaskColumns === "function") {
          window.__fitGanttTaskColumns(document);
        }
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
      var execDoc = document.querySelector(".exec-doc-scroll-wrap");
      if (execDoc) {
        try {
          var feEx2 = window.frameElement;
          if (feEx2) {
            feEx2.style.setProperty("width", "100%", "important");
            feEx2.style.setProperty("max-width", "100%", "important");
            feEx2.style.setProperty("display", "block", "important");
          }
        } catch (e) {}
        execDoc.style.setProperty("width", "100%", "important");
        execDoc.style.setProperty("max-width", "100%", "important");
        var exH2 = Math.ceil(execDoc.getBoundingClientRect().height) + 24;
        if (exH2 > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: exH2 }, "*");
          return;
        }
      }
      var fc = document.querySelector(".fc-table-scroll-wrap")
        || document.querySelector(".pred-detail-wrap");
      if (fc) {
        try {
          var feFc = window.frameElement;
          if (feFc) {
            feFc.style.setProperty("width", "100%", "important");
            feFc.style.setProperty("max-width", "100%", "important");
            feFc.style.setProperty("display", "block", "important");
          }
        } catch (e) {}
        fc.style.setProperty("width", "100%", "important");
        fc.style.setProperty("max-width", "100%", "important");
        var fcTbl = fc.querySelector("table");
        var fcLight = !!(document.querySelector(".gdrs-light-table, .bi-light-table"));
        if (fcTbl) {
          if (fcLight) {
            fcTbl.style.setProperty("width", "max-content", "important");
            fcTbl.style.setProperty("min-width", "100%", "important");
            fcTbl.style.setProperty("table-layout", "auto", "important");
          } else {
            fcTbl.style.setProperty("width", "100%", "important");
            fcTbl.style.setProperty("min-width", "100%", "important");
            fcTbl.style.setProperty("max-width", "100%", "important");
            fcTbl.style.setProperty("table-layout", "fixed", "important");
          }
        }
        var fcRoot = document.querySelector(".bi-sortable-html-root");
        if (fcRoot) {
          fcRoot.style.setProperty("width", "100%", "important");
          fcRoot.style.setProperty("max-width", "100%", "important");
        }
        var parentH = 0;
        try {
          if (window.frameElement && window.frameElement.clientHeight) parentH = window.frameElement.clientHeight;
        } catch (e) {}
        var vhFc2 = parseFloat(fc.getAttribute("data-scroll-vh") || "0");
        var fh;
        if (vhFc2 > 0) {
          // длинная скролл-таблица (plan/fact): занять высоту вьюпорта
          if (parentH <= 120 && window.innerHeight) {
            parentH = Math.min(window.innerHeight * vhFc2 / 100, window.innerHeight * 0.92);
          }
          fh = parentH > 120 ? parentH : Math.ceil(Math.max(280, vhFc2 * window.innerHeight / 100 + 12));
        } else {
          // self-size (обёртка height:auto + max-height): высота по контенту,
          // а не echo текущего clientHeight — иначе iframe залипает на завышенной
          // стартовой высоте и появляется пустота перед кнопкой «Скачать таблицу».
          fh = Math.ceil(fc.getBoundingClientRect().height) + 12;
        }
        if (fh > 0) {
          window.parent.postMessage({ type: "streamlit:setFrameHeight", height: fh }, "*");
          return;
        }
      }
      var bts = document.querySelector(".budget-table-scroll");
      if (bts) {
        var boxAttr2 = parseInt(bts.getAttribute("data-scroll-box-h") || "0", 10);
        if (boxAttr2 > 0) {
          bts.style.setProperty("height", boxAttr2 + "px", "important");
          bts.style.setProperty("max-height", boxAttr2 + "px", "important");
          bts.style.setProperty("min-height", "0", "important");
          bts.style.setProperty("overflow-x", "auto", "important");
          bts.style.setProperty("overflow-y", "auto", "important");
          if (bts.classList.contains("pred-detail-scroll") || bts.classList.contains("budget-table-scroll")) {
            bts.style.setProperty("padding-bottom", "16px", "important");
            bts.style.setProperty("scroll-padding-bottom", "16px", "important");
          }
          if (bts.classList.contains("pred-detail-scroll")) {
            bts.style.setProperty("margin", "0", "important");
            bts.style.setProperty("overflow-x", "scroll", "important");
          }
        }
        var parentH2 = 0;
        try {
          if (window.frameElement && window.frameElement.clientHeight) parentH2 = window.frameElement.clientHeight;
        } catch (e) {}
        var vhAttr = parseFloat(bts.getAttribute("data-scroll-vh") || "0");
        var capPx = 0;
        if (vhAttr > 0 && window.innerHeight) {
          capPx = Math.min(window.innerHeight * vhAttr / 100, window.innerHeight * 0.92);
        }
        var bsh = boxAttr2 > 0 ? boxAttr2 : (parentH2 > 120 ? parentH2
          : (capPx > 0 ? Math.ceil(Math.max(280, capPx + 12)) : 320));
        if (bts.classList.contains("pred-detail-scroll") && bsh > 0) {
          bsh = bsh + 16;
        }
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
      var pad = 4;
      if (root && root.classList) {
        if (root.classList.contains("pred-detail-wrap") || root.classList.contains("fc-table-scroll-wrap")) {
          pad = 20;
        } else if (root.classList.contains("budget-deviation-table-wrap") && !document.querySelector(".budget-table-scroll")) {
          pad = 18;
        }
      }
      var h = 0;
      var cap = root.querySelector && root.querySelector(".budget-table-scroll");
      if (cap && root.classList.contains("budget-deviation-table-wrap")) {
        var boxAttr3 = parseInt(cap.getAttribute("data-scroll-box-h") || "0", 10);
        var parentH3 = 0;
        try {
          if (window.frameElement && window.frameElement.clientHeight) parentH3 = window.frameElement.clientHeight;
        } catch (e) {}
        h = boxAttr3 > 0 ? boxAttr3 : (parentH3 > 120 ? parentH3 : 320);
      } else if (cap) {
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
.pf-dates-table-wrap{
  display:block;width:100%;max-width:100%;margin:0;padding:0;
  overflow-x:visible!important;overflow-y:visible;
  -webkit-overflow-scrolling:touch;scrollbar-gutter:stable;
}
.gantt-schedule-table-wrap{
  display:block;width:max-content!important;min-width:100%!important;max-width:none!important;
  margin:0;padding:0;box-sizing:border-box;
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
.bi-sortable-html-root:has(.exec-doc-scroll-wrap){overflow:visible!important;overflow-x:hidden!important}
html:has(.exec-doc-scroll-wrap),body:has(.exec-doc-scroll-wrap){overflow:hidden!important;margin:0;padding:0}
.exec-doc-scroll-wrap{
  display:block;width:100%!important;margin:0;padding:0;
  height:min(70vh,520px)!important;max-height:min(70vh,520px)!important;
  overflow-x:auto!important;overflow-y:scroll!important;
  scrollbar-gutter:stable;scrollbar-width:thin;
}
.exec-doc-scroll-wrap table{width:100%!important;min-width:100%!important;table-layout:fixed!important}
.exec-doc-scroll-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;vertical-align:middle!important;text-align:center!important}
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
.pd-dynamics-scroll-wrap{display:block!important;width:100%!important;max-width:100%!important;min-height:0!important;height:auto!important;max-height:640px!important;overflow-y:auto!important;overflow-x:auto!important;-webkit-overflow-scrolling:touch!important;scrollbar-gutter:stable!important;scrollbar-width:thin!important;scrollbar-color:#4a5568 #1a1c23!important;border:1px solid rgba(255,255,255,0.25)!important;border-radius:10px!important;margin:0.35em 0 0 0!important;box-sizing:border-box!important;}
.pd-dynamics-scroll-wrap[data-scroll-box-h],
.pd-dynamics-scroll-wrap[data-pd-box-h]{min-height:0!important;height:auto!important;max-height:640px!important;}
.pd-dynamics-scroll-wrap thead th,.pd-dynamics-table-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;vertical-align:middle!important;text-align:center!important;background:hsl(209,72%,6%)!important;overflow:visible!important;text-overflow:clip!important;white-space:nowrap!important;}
.pd-dynamics-scroll-wrap thead th .bi-sort-label,.pd-dynamics-table-wrap thead th .bi-sort-label{white-space:nowrap!important;overflow:visible!important;flex:0 0 auto!important;display:inline-block!important;text-align:center!important;width:100%!important;}
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
.bi-sortable-html-root > .bi-light-table:has(.budget-deviation-table-wrap),
.bi-sortable-html-root > .bi-light-table:has(.budget-table-scroll),
.bi-sortable-html-root > .gdrs-light-table:has(.budget-deviation-table-wrap){
  display:block!important;width:100%!important;max-width:100%!important;
  height:auto!important;min-height:0!important;overflow:visible!important;
}
.bi-sortable-html-root:has(.budget-table-scroll){
  overflow:hidden!important;height:100%!important;max-height:100%!important;min-height:0!important;
}
html:has(.budget-table-scroll),body:has(.budget-table-scroll){
  overflow:hidden!important;margin:0;padding:0;height:100%!important;min-height:0!important;
}
.budget-deviation-table-wrap:not(:has(.budget-table-scroll)){
  display:block!important;height:auto!important;max-height:none!important;min-height:0!important;
  overflow:visible!important;width:100%!important;max-width:100%!important;box-sizing:border-box;
}
.budget-deviation-table-wrap:has(.budget-table-scroll){
  display:flex!important;flex-direction:column!important;height:100%!important;min-height:0!important;
  overflow:hidden!important;width:100%!important;max-width:100%!important;box-sizing:border-box;
}
.budget-table-scroll{
  display:block!important;width:100%!important;min-height:0!important;
  overflow:auto!important;-webkit-overflow-scrolling:touch!important;
  scrollbar-gutter:stable;scrollbar-width:thin;box-sizing:border-box;
  padding-bottom:14px!important;scroll-padding-bottom:14px!important;
}
.budget-table-scroll table{width:max-content!important;min-width:100%!important;table-layout:auto!important}
.budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important}
.budget-table-scroll tr.bd-total-row td{position:sticky!important;bottom:0!important;z-index:4!important;
  box-shadow:0 -3px 10px rgba(0,0,0,0.35)!important}
.budget-table-scroll.pred-detail-scroll{
  margin:0!important;width:100%!important;max-width:100%!important;
  overflow-x:scroll!important;overflow-y:auto!important;
  padding-bottom:16px!important;scroll-padding-bottom:16px!important;box-sizing:border-box!important;
}
.budget-table-scroll.pred-detail-scroll::-webkit-scrollbar{width:10px;height:12px;}
.budget-table-scroll.pred-detail-scroll::-webkit-scrollbar-thumb{background:#4a5568;border-radius:6px;}
.budget-table-scroll.pred-detail-scroll::-webkit-scrollbar-track{background:#1a1c23;}

.fc-table-scroll-wrap table,
.fc-table-scroll-wrap.bi-styled-table-wrap table,
.bi-sortable-html-root:has(.fc-table-scroll-wrap) table{
  width:max-content!important;min-width:100%!important;table-layout:auto!important;
}
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
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table.bi-sortable-table{min-width:max-content!important;}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table.bi-sortable-table,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table.rendered-table,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table.pf-dates-table,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table.gantt-schedule-table{
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
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-pf-end,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-pf-dur,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-pf-dur{
  max-width:none!important; white-space:nowrap!important;
}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-task,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-task{
  overflow:visible!important; text-overflow:clip!important;
  white-space:nowrap!important; text-align:left!important; box-sizing:border-box!important;
}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-task > div,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-task .bi-sort-label{
  width:auto!important;flex:0 0 auto!important;white-space:nowrap!important;
}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-pf-project,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-pf-project,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-text,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-text{
  /* Наименование проекта и прочий текст — полностью, горизонтальный скролл таблицы. */
  max-width:none!important; overflow:visible!important; text-overflow:clip!important;
  white-space:nowrap!important; text-align:left!important;
}
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-reason,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-reason,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table th.col-gantt-notes,
.bi-sortable-html-root:has(.gantt-schedule-table-wrap) table td.col-gantt-notes{
  min-width:10em; max-width:22em!important; white-space:normal!important;
  word-wrap:break-word!important; overflow-wrap:anywhere!important; text-align:center!important;
  background:transparent!important; background-color:transparent!important;
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
.bi-sortable-html-root:has(.pd-dynamics-scroll-wrap) table th,
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table th{
  text-align:center!important;vertical-align:middle!important;
}
.bi-sortable-html-root:has(.pd-dynamics-scroll-wrap) table th .bi-sort-label,
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table th .bi-sort-label{
  text-align:center!important;width:100%!important;display:inline-block!important;
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
.bi-sortable-html-root { width: 100%; max-width: 100%; color: #111827; }
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

_FINANCE_BUDGET_IFRAME_SHELL_CSS_LIGHT = """
<style>
.bi-sortable-html-root > .bi-light-table:has(.budget-deviation-table-wrap),
.bi-sortable-html-root > .bi-light-table:has(.budget-table-scroll),
.bi-sortable-html-root > .gdrs-light-table:has(.budget-deviation-table-wrap){
  display:block!important;width:100%!important;max-width:100%!important;
  height:auto!important;min-height:0!important;overflow:visible!important;
}
.bi-sortable-html-root:has(.budget-table-scroll){
  overflow:hidden!important;height:100%!important;max-height:100%!important;min-height:0!important;
}
html:has(.budget-table-scroll),body:has(.budget-table-scroll){
  overflow:hidden!important;margin:0;padding:0;height:100%!important;min-height:0!important;
  background:#ffffff!important;color:#111827!important;
}
.budget-deviation-table-wrap:not(:has(.budget-table-scroll)){
  display:block!important;height:auto!important;max-height:none!important;min-height:0!important;
  overflow:visible!important;width:100%!important;max-width:100%!important;box-sizing:border-box;
}
.budget-deviation-table-wrap:has(.budget-table-scroll){
  display:flex!important;flex-direction:column!important;height:100%!important;min-height:0!important;
  overflow:hidden!important;width:100%!important;max-width:100%!important;box-sizing:border-box;
}
.budget-table-scroll{
  display:block!important;width:100%!important;min-height:0!important;
  overflow:auto!important;-webkit-overflow-scrolling:touch!important;
  scrollbar-gutter:stable;scrollbar-width:thin;box-sizing:border-box;
  scrollbar-color:#94a3b8 #e5e7eb!important;
  padding-bottom:14px!important;scroll-padding-bottom:14px!important;
}
.budget-table-scroll table{width:max-content!important;min-width:100%!important;table-layout:auto!important}
.budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important}
.budget-table-scroll tr.bd-total-row td{position:sticky!important;bottom:0!important;z-index:4!important;
  background-color:#e5e7eb!important;color:#111827!important;
  box-shadow:0 -3px 10px rgba(15,23,42,0.12)!important}
.budget-table-scroll tr.bd-total-row td,.budget-table-scroll tr.bd-total-row td *{
  color:#111827!important;-webkit-text-fill-color:#111827!important}
.budget-table-scroll tr.bd-group-row td{background-color:#f3f4f6!important;color:#111827!important}
.budget-table-scroll thead th{background-color:#f3f4f6!important;color:#111827!important}
.budget-table-scroll tbody td:not(.fc-st-cell-red):not(.fc-st-cell-green):not(.bd-cell-red):not(.bd-cell-green){color:#111827!important}
.budget-table-scroll td.bd-cell-red,.budget-table-scroll td.bd-cell-red *{color:hsl(348,100%,63%)!important;-webkit-text-fill-color:hsl(348,100%,63%)!important;}
.budget-table-scroll td.bd-cell-green,.budget-table-scroll td.bd-cell-green *{color:#15803d!important;-webkit-text-fill-color:#15803d!important;}
.budget-table-scroll tr.bd-total-row td.bd-cell-red,.budget-table-scroll tr.bd-total-row td.bd-cell-red *{
  color:hsl(348,100%,63%)!important;-webkit-text-fill-color:hsl(348,100%,63%)!important;}
.budget-table-scroll tr.bd-total-row td.bd-cell-green,.budget-table-scroll tr.bd-total-row td.bd-cell-green *{
  color:#15803d!important;-webkit-text-fill-color:#15803d!important;}
.fc-st-cell-red,.fc-st-cell-red *{color:hsl(348,100%,63%)!important;-webkit-text-fill-color:hsl(348,100%,63%)!important;}
.fc-st-cell-green,.fc-st-cell-green *{color:#15803d!important;-webkit-text-fill-color:#15803d!important;}
.pred-detail-scroll tbody tr.pred-row-overdue td{background:rgba(254,226,226,0.78)!important;}
.pred-detail-scroll tbody tr.pred-row-resolved td{background:rgba(220,252,231,0.85)!important;}
.pred-detail-scroll tbody tr:not(.pred-row-overdue):not(.pred-row-resolved) td{background:#ffffff!important;}
.pred-detail-scroll .pred-chip-overdue{background:#ffedd5!important;color:#9a3412!important;border-color:#fdba74!important;}
.pred-detail-scroll .pred-chip-ok{background:#dcfce7!important;color:#166534!important;border-color:#86efac!important;}
.pred-detail-scroll .pred-chip-warn{background:#fef3c7!important;color:#92400e!important;border-color:#fbbf24!important;}
.pred-detail-scroll .pred-days-neg{background:#fee2e2!important;color:#b91c1c!important;}
.pred-detail-scroll .pred-days-ok{background:#dcfce7!important;color:#166534!important;}
.budget-table-scroll.pred-detail-scroll{
  margin:0!important;width:100%!important;max-width:100%!important;
  overflow-x:scroll!important;overflow-y:auto!important;
  padding-bottom:16px!important;scroll-padding-bottom:16px!important;box-sizing:border-box!important;
}
.budget-table-scroll.pred-detail-scroll::-webkit-scrollbar{width:10px;height:12px;}
.budget-table-scroll.pred-detail-scroll::-webkit-scrollbar-thumb{background:#94a3b8;border-radius:6px;}
.budget-table-scroll.pred-detail-scroll::-webkit-scrollbar-track{background:#e5e7eb;}
</style>
"""

_FINANCE_FC_TABLE_IFRAME_SHELL_CSS_LIGHT = """
<style>
.bi-sortable-html-root:has(.fc-table-scroll-wrap){
  overflow:hidden!important;height:100%!important;max-height:100%!important;min-height:0!important;
}
html:has(.fc-table-scroll-wrap),body:has(.fc-table-scroll-wrap){
  overflow:hidden!important;margin:0;padding:0;height:100%!important;min-height:0!important;
  background:#ffffff!important;color:#111827!important;
}
.fc-table-scroll-wrap{
  display:block!important;width:100%!important;height:100%!important;max-height:100%!important;
  min-height:0!important;overflow-x:auto!important;overflow-y:auto!important;
  -webkit-overflow-scrolling:touch!important;scrollbar-gutter:stable;scrollbar-width:thin;
  scrollbar-color:#94a3b8 #f3f4f6!important;
  border:1px solid #cbd5e1!important;border-radius:10px!important;box-sizing:border-box;
}
.fc-table-scroll-wrap thead th{
  position:sticky!important;top:0!important;z-index:5!important;
  background-color:#f3f4f6!important;color:#111827!important;
}
.fc-table-scroll-wrap tbody td:not(.fc-st-cell-red):not(.fc-st-cell-green){
  color:#111827!important;-webkit-text-fill-color:#111827!important;border-color:#cbd5e1!important;
}
.fc-table-scroll-wrap tbody td.fc-st-cell-red,
.fc-table-scroll-wrap tbody td.fc-st-cell-green{
  border-color:#cbd5e1!important;
}
.fc-table-scroll-wrap tr.bd-total-row td{
  background-color:#e5e7eb!important;color:#111827!important;
  border-top:3px solid #94a3b8!important;
  box-shadow:0 -3px 10px rgba(15,23,42,0.08)!important;
}
.fc-table-scroll-wrap tr.bd-total-row td,.fc-table-scroll-wrap tr.bd-total-row td *{
  color:#111827!important;-webkit-text-fill-color:#111827!important;
}
.fc-table-scroll-wrap table,
.fc-table-scroll-wrap.bi-styled-table-wrap table{
  width:max-content!important;min-width:100%!important;table-layout:auto!important;
}
.fc-st-cell-red,.fc-st-cell-red *{color:hsl(348,100%,63%)!important;-webkit-text-fill-color:hsl(348,100%,63%)!important;}
.fc-st-cell-green,.fc-st-cell-green *{color:#15803d!important;-webkit-text-fill-color:#15803d!important;}
</style>
"""

_GANTT_SCHEDULE_IFRAME_SHELL_CSS_LIGHT = """
<style>
html:has(.gantt-schedule-scroll-wrap),body:has(.gantt-schedule-scroll-wrap){
  overflow:hidden!important;margin:0;padding:0;height:auto!important;min-height:0!important;
  background:#ffffff!important;color:#111827!important;
}
.bi-sortable-html-root:has(.gantt-schedule-scroll-wrap){
  overflow:hidden!important;height:auto!important;max-height:none!important;min-height:0!important;
}
.gantt-schedule-scroll-wrap{
  display:block!important;width:100%!important;max-width:100%!important;min-height:0!important;
  overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;
  scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:#94a3b8 #e5e7eb!important;
  box-sizing:border-box!important;
}
.gantt-schedule-scroll-wrap[data-scroll-box-h]{
  height:auto!important;max-height:none!important;
}
.gantt-schedule-scroll-wrap thead th{
  position:sticky!important;top:0!important;z-index:5!important;
  background-color:#f3f4f6!important;color:#111827!important;
}
.gantt-schedule-scroll-wrap tbody td:not(.pf-dev-red):not(.pf-dev-green){
  color:#111827!important;-webkit-text-fill-color:#111827!important;
  border-color:#cbd5e1!important;
}
.gantt-schedule-scroll-wrap tr.bd-group-row td{
  background-color:#f3f4f6!important;color:#111827!important;
}
.gantt-schedule-scroll-wrap tr:hover td{background-color:#f9fafb!important;}
.gantt-schedule-scroll-wrap tr:nth-child(even) td{background-color:#fcfcfd!important;}
.gantt-schedule-scroll-wrap .rendered-table th{
  background:#f3f4f6!important;color:#111827!important;border-bottom:2px solid #cbd5e1!important;
}
.gantt-schedule-scroll-wrap .rendered-table td{
  color:#111827!important;border-bottom:1px solid #cbd5e1!important;
}
.gantt-schedule-scroll-wrap .pf-dev-red,.gantt-schedule-scroll-wrap .pf-dev-red *{
  color:hsl(348,100%,63%)!important;-webkit-text-fill-color:hsl(348,100%,63%)!important;
}
.gantt-schedule-scroll-wrap .pf-dev-green,.gantt-schedule-scroll-wrap .pf-dev-green *{
  color:#166534!important;-webkit-text-fill-color:#166534!important;font-weight:700!important;
}
.gantt-schedule-table-wrap{width:max-content!important;min-width:100%!important;max-width:none!important;}
.gantt-schedule-table-wrap table{width:max-content!important;min-width:100%!important;table-layout:auto!important;}
</style>
"""

_DEV_REASONS_IFRAME_SHELL_CSS_LIGHT = """
<style>
html:has(.dev-reasons-wrap),body:has(.dev-reasons-wrap),
html:has(.dev-maket-table-wrap),body:has(.dev-maket-table-wrap){
  overflow:hidden!important;margin:0;padding:0;height:auto!important;min-height:0!important;
  background:#ffffff!important;color:#111827!important;
}
.bi-sortable-html-root:has(.dev-reasons-wrap),
.bi-sortable-html-root:has(.dev-maket-table-wrap){
  overflow:hidden!important;height:auto!important;max-height:none!important;min-height:0!important;
}
.dev-reasons-wrap,.pred-detail-wrap.dev-maket-table-wrap{
  display:block!important;width:100%!important;max-width:100%!important;min-height:0!important;
  overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;
  scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:#94a3b8 #e5e7eb!important;
  box-sizing:border-box!important;
}
.dev-reasons-wrap[data-scroll-box-h],
.pred-detail-wrap.dev-maket-table-wrap[data-scroll-box-h]{
  height:auto!important;max-height:none!important;
}
.dev-reasons-wrap thead th,.pred-detail-wrap.dev-maket-table-wrap thead th,
.dev-reasons-table th{
  position:sticky!important;top:0!important;z-index:5!important;
  background-color:#f3f4f6!important;color:#111827!important;
}
.dev-reasons-wrap tbody td,.pred-detail-wrap.dev-maket-table-wrap tbody td,
.dev-reasons-table td:not(.dev-txt-bad):not(.dev-txt-ok):not(.dev-txt-zero){
  color:#111827!important;border-bottom:1px solid #cbd5e1!important;
}
.dev-reasons-wrap .dev-txt-bad,.dev-reasons-table .dev-txt-bad,
.dev-reasons-wrap .dev-txt-bad *{
  color:hsl(348,100%,63%)!important;-webkit-text-fill-color:hsl(348,100%,63%)!important;
}
.dev-reasons-wrap .dev-txt-ok,.dev-reasons-table .dev-txt-ok,
.dev-reasons-wrap .dev-txt-ok *{
  color:#15803d!important;-webkit-text-fill-color:#15803d!important;
}
.dev-reasons-wrap .dev-txt-zero,.dev-reasons-table .dev-txt-zero{
  color:#6b7280!important;
}
.pred-detail-wrap.dev-maket-table-wrap .rendered-table th{
  background:#f3f4f6!important;color:#111827!important;border-bottom:2px solid #cbd5e1!important;
}
.pred-detail-wrap.dev-maket-table-wrap .rendered-table td{
  color:#111827!important;border-bottom:1px solid #cbd5e1!important;
}
.pred-detail-wrap.dev-maket-table-wrap .rendered-table tr:hover td{background:#f9fafb!important;}
</style>
"""

_PRED_DETAIL_IFRAME_SHELL_CSS_LIGHT = """
<style>
html:has(.pred-detail-wrap:not(.dev-maket-table-wrap)),body:has(.pred-detail-wrap:not(.dev-maket-table-wrap)){
  overflow:hidden!important;margin:0;padding:0;height:100%!important;min-height:0!important;
  background:#ffffff!important;color:#111827!important;
}
.bi-sortable-html-root:has(.pred-detail-wrap:not(.dev-maket-table-wrap)){
  overflow:hidden!important;height:100%!important;max-height:100%!important;min-height:0!important;
}
.pred-detail-wrap:not(.dev-maket-table-wrap){
  display:block!important;width:100%!important;height:100%!important;max-height:100%!important;
  min-height:0!important;overflow-x:auto!important;overflow-y:auto!important;
  -webkit-overflow-scrolling:touch!important;scrollbar-gutter:stable;scrollbar-width:thin;
  scrollbar-color:#94a3b8 #e5e7eb!important;border:1px solid #cbd5e1!important;
  border-radius:10px!important;box-sizing:border-box!important;
}
.pred-detail-wrap:not(.dev-maket-table-wrap) thead th{
  position:sticky!important;top:0!important;z-index:5!important;
  background-color:#f3f4f6!important;color:#111827!important;
}
.pred-detail-wrap:not(.dev-maket-table-wrap) tbody td{
  color:#111827!important;-webkit-text-fill-color:#111827!important;
  border-color:#cbd5e1!important;
}
.pred-detail-wrap:not(.dev-maket-table-wrap) tbody tr.pred-row-overdue td{
  background:rgba(254,226,226,0.78)!important;
}
.pred-detail-wrap:not(.dev-maket-table-wrap) tbody tr.pred-row-resolved td{
  background:rgba(220,252,231,0.85)!important;
}
.pred-detail-wrap:not(.dev-maket-table-wrap) tbody tr:not(.pred-row-overdue):not(.pred-row-resolved) td{
  background:#ffffff!important;
}
.pred-detail-wrap:not(.dev-maket-table-wrap) table{
  width:max-content!important;min-width:100%!important;table-layout:auto!important;
}
</style>
"""

_EXEC_DOC_IFRAME_SHELL_CSS_LIGHT = """
<style>
html:has(.exec-doc-scroll-wrap),body:has(.exec-doc-scroll-wrap){
  overflow:hidden!important;margin:0;padding:0;height:100%!important;min-height:0!important;
  background:#ffffff!important;color:#111827!important;
}
.bi-sortable-html-root:has(.exec-doc-scroll-wrap){
  overflow:hidden!important;height:100%!important;max-height:100%!important;min-height:0!important;
}
.exec-doc-scroll-wrap{
  display:block!important;width:100%!important;max-width:100%!important;min-height:0!important;
  overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;
  scrollbar-gutter:stable!important;scrollbar-width:thin!important;
  scrollbar-color:#94a3b8 #e5e7eb!important;border:1px solid #cbd5e1!important;
  border-radius:14px!important;box-sizing:border-box!important;
  padding-bottom:14px!important;scroll-padding-bottom:14px!important;
}
.exec-doc-scroll-wrap[data-scroll-box-h]{
  height:auto!important;max-height:none!important;
}
.exec-doc-scroll-wrap thead th{
  position:sticky!important;top:0!important;z-index:5!important;
  background-color:#f3f4f6!important;color:#111827!important;
}
.exec-doc-scroll-wrap tbody td{
  color:#111827!important;-webkit-text-fill-color:#111827!important;
  border-color:#e2e8f0!important;background:#ffffff!important;
}
.exec-doc-scroll-wrap tbody tr:nth-child(even) td{background:#f9fafb!important;}
.exec-doc-scroll-wrap tbody tr:hover td{background:#f3f4f6!important;}
.exec-doc-scroll-wrap table{
  width:100%!important;min-width:100%!important;table-layout:fixed!important;
}
.exec-doc-scroll-wrap .exec-pill-signed{background:#dcfce7!important;color:#166534!important;border-color:#86efac!important;}
.exec-doc-scroll-wrap .exec-pill-customer{background:#fef3c7!important;color:#92400e!important;border-color:#fbbf24!important;}
.exec-doc-scroll-wrap .exec-pill-contractor{background:#dbeafe!important;color:#1e40af!important;border-color:#93c5fd!important;}
.exec-doc-scroll-wrap .exec-pill-declined{background:#fee2e2!important;color:#b91c1c!important;border-color:#fca5a5!important;}
.exec-doc-scroll-wrap .exec-pill-default{background:#f3f4f6!important;color:#374151!important;border-color:#cbd5e1!important;}
.exec-doc-scroll-wrap .exec-delay-val{color:#0d9488!important;}
</style>
"""

_PF_DATES_IFRAME_SHELL_CSS_LIGHT = """
<style>
html:has(.pf-dates-scroll-wrap),body:has(.pf-dates-scroll-wrap),
html:has(.pf-covenant-table-wrap),body:has(.pf-covenant-table-wrap),
html:has(.pf-zos-table-wrap),body:has(.pf-zos-table-wrap),
html:has(.pf-dates-table-wrap),body:has(.pf-dates-table-wrap){
  overflow:hidden!important;margin:0;padding:0;height:auto!important;min-height:0!important;
  background:#ffffff!important;color:#111827!important;
}
.bi-sortable-html-root:has(.pf-dates-scroll-wrap),
.bi-sortable-html-root:has(.pf-covenant-table-wrap),
.bi-sortable-html-root:has(.pf-zos-table-wrap),
.bi-sortable-html-root:has(.pf-dates-table-wrap){
  overflow:hidden!important;height:auto!important;max-height:none!important;min-height:0!important;
}
.pf-dates-scroll-wrap{
  display:block!important;width:100%!important;max-width:100%!important;min-height:0!important;
  overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;
  scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:#94a3b8 #e5e7eb!important;
  box-sizing:border-box!important;
}
.pf-dates-scroll-wrap[data-scroll-box-h]{
  height:auto!important;max-height:none!important;
}
.pf-dates-scroll-wrap thead th,
.pf-covenant-table-wrap thead th,
.pf-zos-table-wrap thead th,
.pf-dates-table-wrap thead th{
  position:sticky!important;top:0!important;z-index:5!important;
  background-color:#f3f4f6!important;color:#111827!important;
}
.pf-dates-scroll-wrap tbody td:not(.pf-dev-red):not(.pf-dev-green),
.pf-covenant-table-wrap tbody td:not(.pf-dev-red):not(.pf-dev-green),
.pf-zos-table-wrap tbody td:not(.pf-dev-red):not(.pf-dev-green),
.pf-dates-table-wrap tbody td:not(.pf-dev-red):not(.pf-dev-green){
  color:#111827!important;-webkit-text-fill-color:#111827!important;
  border-color:#cbd5e1!important;
}
.pf-dates-scroll-wrap tr:hover td,
.pf-covenant-table-wrap tr:hover td,
.pf-zos-table-wrap tr:hover td,
.pf-dates-table-wrap tr:hover td{background-color:#f9fafb!important;}
.pf-dates-scroll-wrap tr:nth-child(even) td,
.pf-covenant-table-wrap tr:nth-child(even) td,
.pf-zos-table-wrap tr:nth-child(even) td,
.pf-dates-table-wrap tr:nth-child(even) td{background-color:#fcfcfd!important;}
.pf-dates-scroll-wrap .pf-dev-red,.pf-dates-scroll-wrap .pf-dev-red *,
.pf-covenant-table-wrap .pf-dev-red,.pf-covenant-table-wrap .pf-dev-red *,
.pf-zos-table-wrap .pf-dev-red,.pf-zos-table-wrap .pf-dev-red *,
.pf-dates-table-wrap .pf-dev-red,.pf-dates-table-wrap .pf-dev-red *{
  color:hsl(348,100%,63%)!important;-webkit-text-fill-color:hsl(348,100%,63%)!important;
}
.pf-dates-scroll-wrap .pf-dev-green,.pf-dates-scroll-wrap .pf-dev-green *,
.pf-covenant-table-wrap .pf-dev-green,.pf-covenant-table-wrap .pf-dev-green *,
.pf-zos-table-wrap .pf-dev-green,.pf-zos-table-wrap .pf-dev-green *,
.pf-dates-table-wrap .pf-dev-green,.pf-dates-table-wrap .pf-dev-green *{
  color:#166534!important;-webkit-text-fill-color:#166534!important;font-weight:700!important;
}
.pf-dates-scroll-wrap .rendered-table th,
.pf-covenant-table-wrap .rendered-table th,
.pf-zos-table-wrap .rendered-table th,
.pf-dates-table-wrap .rendered-table th{
  background:#f3f4f6!important;color:#111827!important;border-bottom:2px solid #cbd5e1!important;
}
.pf-dates-scroll-wrap .rendered-table td,
.pf-covenant-table-wrap .rendered-table td,
.pf-zos-table-wrap .rendered-table td,
.pf-dates-table-wrap .rendered-table td{
  color:#111827!important;border-bottom:1px solid #cbd5e1!important;
}
.bi-sortable-html-root:has(.pf-dates-scroll-wrap) table.pf-dates-table,
.bi-sortable-html-root:has(.pf-covenant-table-wrap) table.pf-dates-table{
  width:max-content!important;min-width:100%!important;max-width:none!important;
}
.bi-sortable-html-root:has(.pf-covenant-table-wrap) table.pf-dates-table{
  width:100%!important;min-width:100%!important;max-width:100%!important;
}
</style>
"""

_PD_DYNAMICS_IFRAME_SHELL_CSS_LIGHT = """
<style>
html:has(.pd-dynamics-scroll-wrap),body:has(.pd-dynamics-scroll-wrap),
html:has(.pd-dynamics-table-wrap),body:has(.pd-dynamics-table-wrap){
  overflow:hidden!important;margin:0;padding:0;height:auto!important;min-height:0!important;
  background:#ffffff!important;color:#111827!important;
}
.bi-sortable-html-root:has(.pd-dynamics-scroll-wrap),
.bi-sortable-html-root:has(.pd-dynamics-table-wrap){
  overflow:hidden!important;height:auto!important;max-height:none!important;min-height:0!important;
}
.pd-dynamics-scroll-wrap{
  display:block!important;width:100%!important;max-width:100%!important;min-height:0!important;
  height:auto!important;max-height:640px!important;
  overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;
  scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:#94a3b8 #e5e7eb!important;
  border:1px solid #cbd5e1!important;border-radius:10px!important;
  box-sizing:border-box!important;margin:0.35em 0 0 0!important;
}
.pd-dynamics-scroll-wrap[data-scroll-box-h],
.pd-dynamics-scroll-wrap[data-pd-box-h]{
  height:auto!important;max-height:640px!important;min-height:0!important;
  overflow-y:auto!important;overflow-x:auto!important;
}
.pd-dynamics-scroll-wrap thead th,
.pd-dynamics-table-wrap thead th{
  position:sticky!important;top:0!important;z-index:5!important;
  background-color:#f3f4f6!important;color:#111827!important;
  overflow:visible!important;text-overflow:clip!important;white-space:nowrap!important;
  text-align:center!important;vertical-align:middle!important;
}
.pd-dynamics-scroll-wrap thead th .bi-sort-label,
.pd-dynamics-table-wrap thead th .bi-sort-label{
  white-space:nowrap!important;overflow:visible!important;text-overflow:clip!important;
  flex:0 0 auto!important;display:inline-block!important;color:#111827!important;
  text-align:center!important;width:100%!important;
}
.pd-dynamics-scroll-wrap tbody td:not(.pf-dev-red):not(.pf-dev-green),
.pd-dynamics-table-wrap tbody td:not(.pf-dev-red):not(.pf-dev-green){
  color:#111827!important;-webkit-text-fill-color:#111827!important;
  border-color:#cbd5e1!important;
}
.pd-dynamics-scroll-wrap tr:hover td,
.pd-dynamics-table-wrap tr:hover td{background-color:#f9fafb!important;}
.pd-dynamics-scroll-wrap tr:nth-child(even) td,
.pd-dynamics-table-wrap tr:nth-child(even) td{background-color:#fcfcfd!important;}
.pd-dynamics-scroll-wrap .pf-dev-red,.pd-dynamics-scroll-wrap .pf-dev-red *,
.pd-dynamics-table-wrap .pf-dev-red,.pd-dynamics-table-wrap .pf-dev-red *{
  color:hsl(348,100%,63%)!important;-webkit-text-fill-color:hsl(348,100%,63%)!important;
}
.pd-dynamics-scroll-wrap .pf-dev-green,.pd-dynamics-scroll-wrap .pf-dev-green *,
.pd-dynamics-table-wrap .pf-dev-green,.pd-dynamics-table-wrap .pf-dev-green *{
  color:#166534!important;-webkit-text-fill-color:#166534!important;font-weight:700!important;
}
.pd-dynamics-scroll-wrap .rendered-table th,
.pd-dynamics-table-wrap .rendered-table th{
  background:#f3f4f6!important;color:#111827!important;border-bottom:2px solid #cbd5e1!important;
}
.pd-dynamics-scroll-wrap .rendered-table td,
.pd-dynamics-table-wrap .rendered-table td{
  color:#111827!important;border-bottom:1px solid #cbd5e1!important;
}
.bi-sortable-html-root:has(.pd-dynamics-scroll-wrap) table.pf-dates-table,
.bi-sortable-html-root:has(.pd-dynamics-table-wrap) table.pf-dates-table{
  width:100%!important;min-width:100%!important;max-width:100%!important;table-layout:fixed!important;
}
</style>
"""


def _iframe_shell_css(html: str) -> str:
    html_l = html or ""
    _light = "gdrs-light-table" in html_l or "bi-light-table" in html_l
    base = _IFRAME_SHELL_CSS_LIGHT if _light else _IFRAME_SHELL_CSS
    if "gdrs-table-wrap" in html_l:
        return base + _GDRS_TABLE_WRAP_IFRAME_CSS
    if _light and "budget-deviation-table-wrap" in html_l:
        return base + _FINANCE_BUDGET_IFRAME_SHELL_CSS_LIGHT
    if _light and "fc-table-scroll-wrap" in html_l:
        return base + _FINANCE_FC_TABLE_IFRAME_SHELL_CSS_LIGHT
    if _light and "gantt-schedule-scroll-wrap" in html_l:
        return base + _GANTT_SCHEDULE_IFRAME_SHELL_CSS_LIGHT
    if _light and ("dev-reasons-wrap" in html_l or "dev-maket-table-wrap" in html_l):
        return base + _DEV_REASONS_IFRAME_SHELL_CSS_LIGHT
    if _light and "pred-detail-wrap" in html_l:
        return base + _PRED_DETAIL_IFRAME_SHELL_CSS_LIGHT
    if _light and "exec-doc-scroll-wrap" in html_l:
        return base + _EXEC_DOC_IFRAME_SHELL_CSS_LIGHT
    if _light and (
        "pf-dates-scroll-wrap" in html_l
        or "pf-covenant-table-wrap" in html_l
        or "pf-zos-table-wrap" in html_l
        or "pf-dates-table-wrap" in html_l
    ):
        return base + _PF_DATES_IFRAME_SHELL_CSS_LIGHT
    if _light and (
        "pd-dynamics-scroll-wrap" in html_l or "pd-dynamics-table-wrap" in html_l
    ):
        return base + _PD_DYNAMICS_IFRAME_SHELL_CSS_LIGHT
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
        # Калибровка по факту (Streamlit не ужимает components.html): строка≈37px
        # (без переносов), thead 1–2 строки. Переполнение уходит во внутренний
        # скролл обёртки — без обрезки и без пустоты под таблицей.
        thead_h = 44
        row_h = 37
        extra = 6
        cap = 1400
    elif "gdrs-matrix-table" in html_l or "gdrs-table-wrap" in html_l:
        thead_h = 132
        row_h = 38
        extra = 56
        cap = 2600
    elif "budget-deviation-table-wrap" in html_l:
        # Калибровка по факту (Streamlit не ужимает components.html): thead≈40px,
        # строка≈34px; итог/группа получают надбавку ниже (+18/+8). Небольшой запас,
        # переполнение уходит во внутренний скролл обёртки (без обрезки и пустоты).
        thead_h = 44
        row_h = 34
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
        thead_h = 48
        row_h = 32
        extra = 16
        cap = 640
    elif "pd-dynamics-table-wrap" in html_l:
        thead_h = 48
        row_h = 32
        extra = 16
        cap = 640
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
    elif "exec-doc-scroll-wrap" in html_l or "pred-detail-wrap" in html_l:
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
    est = thead_h + n_plain * row_h + n_group * (row_h + 8) + n_total * (row_h + 18) + extra
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
    if "dev-reasons-wrap" in html_l:
        return int(max(220, min(620, est + 24)))
    if "dev-maket-table-wrap" in html_l:
        return int(max(280, min(620, est + 24)))
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
    if "exec-doc-scroll-wrap" in html_l or "pred-detail-wrap" in html_l:
        return int(max(420, min(820, est + 24)))
    if "fc-table-scroll-wrap" in html_l:
        m_fc_vh = re.search(r'data-scroll-vh="([\d.]+)"', html_l)
        if m_fc_vh:
            vh_fc = float(m_fc_vh.group(1))
            return int(min(cap, max(280, vh_fc * 10 + 56)))
        return int(min(cap, max(280, est)))
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
                or "gdrs-summary-table-wrap" in html_l
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
        or "exec-doc-scroll-wrap" in html_l
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
    # ГДРС-матрица рендерится через components.html (matrix-fs-root). Host-CSS даёт
    # iframe display:block (без baseline-зазора) и убирает margin/padding контейнера;
    # высоту контейнера по контенту держит _MATRIX_IFRAME_FIT_HEIGHT_SCRIPT внутри iframe.
    if "gdrs-table-wrap" in _b:
        try:
            from dashboards.dev_projects_tz_matrix import (
                _DEV_MATRIX_STREAMLIT_HOST_CSS,
                _DEV_MATRIX_STREAMLIT_HOST_CSS_LIGHT,
            )

            _gdrs_light = "bi-light-table" in _b or "gdrs-light-table" in _b
            st.markdown(
                _DEV_MATRIX_STREAMLIT_HOST_CSS_LIGHT
                if _gdrs_light
                else _DEV_MATRIX_STREAMLIT_HOST_CSS,
                unsafe_allow_html=True,
            )
        except Exception:
            pass
    if "exec-doc-scroll-wrap" in _b:
        _light_exec = "bi-light-table" in _b or "gdrs-light-table" in _b
        _th_bg = "#f3f4f6" if _light_exec else "#16283a"
        _th_fg = "#111827" if _light_exec else "#f8fbff"
        _body_bg = "background:#ffffff!important;color:#111827!important;" if _light_exec else ""
        _m_exec_box = re.search(r'data-scroll-box-h="(\d+)"', html or "")
        _h_exec = int(_m_exec_box.group(1)) if _m_exec_box else 520
        _pad_exec = (
            "padding-bottom:14px!important;scroll-padding-bottom:14px!important;box-sizing:border-box!important;"
            if _light_exec
            else ""
        )
        _iframe_h = _h_exec + 8
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;'
            + _body_bg
            + '}.bi-sortable-html-root{height:100%!important;min-height:0!important;overflow:hidden!important;}'
            f'html body .exec-doc-scroll-wrap{{height:{_h_exec}px!important;max-height:{_h_exec}px!important;'
            f'min-height:0!important;overflow-x:auto!important;overflow-y:auto!important;'
            f'-webkit-overflow-scrolling:touch!important;{_pad_exec}}}'
            'html body .exec-doc-scroll-wrap table{width:100%!important;min-width:100%!important;table-layout:fixed!important;}'
            f'html body .exec-doc-scroll-wrap thead th{{position:sticky!important;top:0!important;z-index:5!important;'
            f'background:{_th_bg}!important;color:{_th_fg}!important;}}'
            '</style></head>',
            1,
        )
        components.html(doc_sc, height=_iframe_h, scrolling=False)
        return
    if "pred-detail-wrap" in _b:
        _dev_maket = "dev-maket-table-wrap" in _b
        _m_box = re.search(r'data-scroll-box-h="(\d+)"', html or "")
        if _dev_maket and _m_box:
            _h_maket = int(_m_box.group(1))
            _light_m = "bi-light-table" in _b or "gdrs-light-table" in _b
            _th_bg = "#f3f4f6" if _light_m else "hsl(209,72%,6%)"
            _th_fg = "#111827" if _light_m else "#fafafa"
            doc_sc = doc.replace(
                "</head>",
                '<style>html,body{height:auto!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
                '.bi-sortable-html-root{height:auto!important;min-height:0!important;overflow:hidden!important;}'
                f'html body .pred-detail-wrap.dev-maket-table-wrap{{height:auto!important;max-height:{_h_maket}px!important;min-height:0!important;'
                'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
                'scrollbar-gutter:stable!important;box-sizing:border-box!important;}}'
                f'html body .pred-detail-wrap.dev-maket-table-wrap thead th{{position:sticky!important;top:0!important;z-index:5!important;'
                f'background:{_th_bg}!important;color:{_th_fg}!important;}}'
                'html body .pred-detail-wrap.dev-maket-table-wrap table{width:max-content!important;min-width:100%!important;table-layout:auto!important;}'
                '</style></head>',
                1,
            )
            components.html(doc_sc, height=_h_maket, scrolling=False)
            return
        _light_pred = "bi-light-table" in _b or "gdrs-light-table" in _b
        _th_bg_p = "#f3f4f6" if _light_pred else "hsl(209,72%,6%)"
        _th_fg_p = "#111827" if _light_pred else "#fafafa"
        _body_bg_p = "background:#ffffff!important;color:#111827!important;" if _light_pred else ""
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;'
            + _body_bg_p
            + '}.bi-sortable-html-root{height:100%!important;min-height:0!important;overflow:hidden!important;}'
            'html body .fc-table-scroll-wrap,html body .pred-detail-wrap,html body .budget-table-scroll{'
            'height:100%!important;max-height:100%!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;}'
            'html body .fc-table-scroll-wrap thead th,html body .pred-detail-wrap thead th,'
            'html body .budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important;'
            'background:' + _th_bg_p + '!important;color:' + _th_fg_p + '!important;}'
            'html body .pred-detail-wrap table{width:max-content!important;min-width:100%!important;table-layout:auto!important;}'
            '</style></head>',
            1,
        )
        components.html(doc_sc, height=584, scrolling=False)
        return
    if "dev-reasons-wrap" in _b and 'data-scroll-box-h="' in (html or ""):
        _m_dev_box = re.search(r'data-scroll-box-h="(\d+)"', html or "")
        _h_dev = int(_m_dev_box.group(1)) if _m_dev_box else int(min(620, max(220, _estimate_html_block_height(html))))
        _light_dev = "bi-light-table" in _b or "gdrs-light-table" in _b
        _th_bg_d = "#f3f4f6" if _light_dev else "#1a1c23"
        _th_fg_d = "#111827" if _light_dev else "#fafafa"
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:auto!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{height:auto!important;min-height:0!important;overflow:hidden!important;}'
            f'html body .dev-reasons-wrap{{height:auto!important;max-height:{_h_dev}px!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
            'scrollbar-gutter:stable!important;box-sizing:border-box!important;}}'
            f'html body .dev-reasons-wrap thead th{{position:sticky!important;top:0!important;z-index:5!important;'
            f'background:{_th_bg_d}!important;color:{_th_fg_d}!important;}}'
            'html body .dev-reasons-wrap table{width:max-content!important;min-width:100%!important;table-layout:auto!important;}'
            '</style></head>',
            1,
        )
        components.html(doc_sc, height=_h_dev, scrolling=False)
        return
    if "pf-dates-scroll-wrap" in _b:
        _h_scroll = min(640, max(280, _estimate_html_block_height(html)))
        components.html(doc, height=_h_scroll, scrolling=False)
        return
    if "gantt-schedule-scroll-wrap" in _b:
        _gantt_light = "bi-light-table" in _b or "gdrs-light-table" in _b
        _gantt_th_bg = "#f3f4f6" if _gantt_light else "hsl(209,72%,6%)"
        _gantt_th_fg = "#111827" if _gantt_light else "#fafafa"
        _m_gantt_box = re.search(r'data-scroll-box-h="(\d+)"', html or "")
        _h_gantt = (
            int(_m_gantt_box.group(1))
            if _m_gantt_box
            else int(min(624, max(180, _estimate_html_block_height(html) + 24)))
        )
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:auto!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{height:auto!important;min-height:0!important;overflow:hidden!important;}'
            f'html body .gantt-schedule-scroll-wrap{{height:{_h_gantt}px!important;max-height:{_h_gantt}px!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
            'scrollbar-gutter:stable!important;box-sizing:border-box!important;}}'
            f'html body .gantt-schedule-scroll-wrap thead th{{position:sticky!important;top:0!important;z-index:5!important;'
            f'background:{_gantt_th_bg}!important;color:{_gantt_th_fg}!important;}}'
            'html body .gantt-schedule-table-wrap{width:max-content!important;min-width:100%!important;max-width:none!important;}'
            'html body .gantt-schedule-table-wrap table{width:max-content!important;min-width:100%!important;table-layout:auto!important;}'
            'html body .gantt-schedule-table-wrap th.col-gantt-task,'
            'html body .gantt-schedule-table-wrap td.col-gantt-task{'
            'white-space:nowrap!important;box-sizing:border-box!important;}'
            'html body .gantt-schedule-table-wrap th.col-gantt-task > div,'
            'html body .gantt-schedule-table-wrap th.col-gantt-task .bi-sort-label{'
            'width:auto!important;flex:0 0 auto!important;white-space:nowrap!important;}'
            '</style></head>',
            1,
        )
        components.html(doc_sc, height=_h_gantt, scrolling=False)
        return
    if "budget-deviation-table-wrap" in _b and "budget-table-scroll" in _b:
        _m_box = re.search(r'data-scroll-box-h="(\d+)"', html or "")
        _m_vh = re.search(r'data-scroll-vh="([\d.]+)"', html or "") or re.search(
            r"max-height:\s*([\d.]+)vh", html or ""
        )
        _vh = float(_m_vh.group(1)) if _m_vh else 52.0
        _h_b = int(_m_box.group(1)) if _m_box else int(min(640, max(280, _vh * 10 + 56)))
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:auto!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{height:auto!important;min-height:0!important;overflow:hidden!important;}'
            'html body .budget-deviation-table-wrap{overflow:hidden!important;width:100%!important;margin:0!important;}'
            f'html body .budget-table-scroll[data-scroll-box-h]{{height:{_h_b}px!important;max-height:{_h_b}px!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
            'scrollbar-gutter:stable!important;box-sizing:border-box!important;padding-bottom:14px!important;scroll-padding-bottom:14px!important;}'
            f'html body .budget-table-scroll.pred-detail-scroll[data-scroll-box-h]{{margin:0!important;width:100%!important;max-width:100%!important;'
            'overflow-x:scroll!important;overflow-y:auto!important;padding-bottom:16px!important;scroll-padding-bottom:16px!important;'
            'scrollbar-gutter:stable!important;}}'
            f'html body .budget-table-scroll:not([data-scroll-box-h]){{height:{_h_b}px!important;max-height:{_h_b}px!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
            'scrollbar-gutter:stable!important;box-sizing:border-box!important;padding-bottom:14px!important;scroll-padding-bottom:14px!important;}'
            'html body .budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important;}'
            'html body .budget-table-scroll tr.bd-total-row td{position:sticky!important;bottom:0!important;z-index:4!important;}'
            'html body .budget-table-scroll table{width:max-content!important;min-width:100%!important;table-layout:auto!important;}'
            '</style></head>',
            1,
        )
        _iframe_h = _h_b + 16 if "pred-detail-scroll" in _b else _h_b
        components.html(doc_sc, height=_iframe_h, scrolling=False)
        return
    if "pd-dynamics-scroll-wrap" in _b:
        _m_pd = re.search(r'data-pd-box-h="(\d+)"', html or "")
        if not _m_pd:
            _m_pd = re.search(r'data-scroll-box-h="(\d+)"', html or "")
        _h_pd = int(_m_pd.group(1)) if _m_pd else min(640, max(120, _estimate_html_block_height(html)))
        _light_pd = "bi-light-table" in (html or "") or "gdrs-light-table" in (html or "")
        _th_bg = (
            "background:#f3f4f6!important;color:#111827!important;"
            if _light_pd
            else "background:hsl(209,72%,6%)!important;"
        )
        _pd_head_css = (
            "<style>html,body{height:auto!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;"
            + ("background:#ffffff!important;color:#111827!important;" if _light_pd else "")
            + ".bi-sortable-html-root{height:auto!important;min-height:0!important;overflow:hidden!important;}"
            + f"html body .pd-dynamics-scroll-wrap{{height:{_h_pd}px!important;max-height:{_h_pd}px!important;min-height:0!important;"
            + "width:100%!important;max-width:100%!important;"
            + "overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;"
            + "scrollbar-gutter:stable!important;box-sizing:border-box!important;}"
            + "html body .pd-dynamics-scroll-wrap .pf-dates-table,"
            + "html body .pd-dynamics-table-wrap .pf-dates-table{"
            + "width:100%!important;min-width:100%!important;max-width:100%!important;table-layout:fixed!important;}"
            + f"html body .pd-dynamics-scroll-wrap thead th{{position:sticky!important;top:0!important;z-index:5!important;text-align:center!important;vertical-align:middle!important;{_th_bg}}}"
            + "html body .pd-dynamics-scroll-wrap thead th .bi-sort-label{text-align:center!important;width:100%!important;display:inline-block!important;}"
            + "</style></head>"
        )
        doc_sc = doc.replace("</head>", _pd_head_css, 1)
        components.html(doc_sc, height=_h_pd, scrolling=False)
        return
    if "fc-table-scroll-wrap" in _b:
        _m_fc_vh = re.search(r'data-scroll-vh="([\d.]+)"', html or "")
        _fc_cap = int(min(640, max(280, (float(_m_fc_vh.group(1)) if _m_fc_vh else 58.0) * 10 + 56)))
        if _m_fc_vh:
            # Явный vh — намеренная скролл-таблица фиксированной высоты.
            _h_fc = _fc_cap
            _fc_root_h = "height:100%!important;"
            _fc_wrap_h = "height:100%!important;max-height:100%!important;"
        else:
            # Без vh (стилизованные сводки, напр. «Сводка по просрочке»): высота по
            # контенту с ограничением-капом, чтобы кнопка «Скачать таблицу» была
            # сразу под таблицей; скролл включается только при переполнении капа.
            _m_fc_rows = re.search(r'data-bi-rows="(\d+)"', html or "")
            _fc_rows = int(_m_fc_rows.group(1)) if _m_fc_rows else 0
            # Высота iframe = это значение (setFrameHeight не ужимает components.html).
            # Калибровка по факту: thead≈44px, строка≈33px; выше капа — внутренний скролл.
            _fc_est = 50 + _fc_rows * 33 if _fc_rows else _fc_cap
            _h_fc = int(max(120, min(_fc_cap, _fc_est)))
            _fc_root_h = "height:auto!important;"
            _fc_wrap_h = f"height:auto!important;max-height:{_fc_cap}px!important;"
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{' + _fc_root_h + 'min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{' + _fc_root_h + 'min-height:0!important;overflow:hidden!important;}'
            'html body .fc-table-scroll-wrap,html body .pred-detail-wrap,html body .budget-table-scroll{'
            + _fc_wrap_h
            + 'min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
            'scrollbar-gutter:stable!important;}'
            'html body .fc-table-scroll-wrap thead th,html body .pred-detail-wrap thead th,'
            'html body .budget-table-scroll thead th{position:sticky!important;top:0!important;z-index:5!important;}'
            'html body .fc-table-scroll-wrap table{width:max-content!important;min-width:100%!important;table-layout:auto!important;}'
            '</style></head>',
            1,
        )
        components.html(doc_sc, height=_h_fc, scrolling=False)
        return
    if "budget-deviation-table-wrap" in _b and "budget-table-scroll" not in _b:
        # Высота iframe = оценка (Streamlit не ужимает components.html). Обёртке даём
        # height:auto + max-height + overflow:auto: короткие таблицы садятся вплотную
        # (кнопка «Скачать таблицу» без пустоты), а если оценка чуть занижена из-за
        # переносимых строк — включается внутренний скролл вместо обрезки контента.
        _h_bd = int(_estimate_html_block_height(html)) + 16
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:auto!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{height:auto!important;min-height:0!important;overflow:hidden!important;}'
            f'html body .budget-deviation-table-wrap:not(:has(.budget-table-scroll)){{height:auto!important;max-height:{_h_bd}px!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
            'scrollbar-gutter:stable!important;box-sizing:border-box!important;}}'
            'html body .budget-deviation-table-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;}'
            '</style></head>',
            1,
        )
        components.html(doc_sc, height=_h_bd, scrolling=False)
        return
    if "gdrs-summary-table-wrap" in _b and "gdrs-table-wrap" not in _b:
        # Высота iframe = оценка (Streamlit не ужимает components.html). Обёртке даём
        # height:auto + max-height + overflow:auto: сводка садится вплотную (кнопка
        # «Скачать таблицу» без пустоты), а при нехватке высоты — внутренний скролл.
        _h_gs = int(_estimate_html_block_height(html)) + 10
        doc_sc = doc.replace(
            "</head>",
            '<style>html,body{height:auto!important;min-height:0!important;overflow:hidden!important;margin:0;padding:0;}'
            '.bi-sortable-html-root{height:auto!important;min-height:0!important;overflow:hidden!important;}'
            f'html body .gdrs-summary-table-wrap{{height:auto!important;max-height:{_h_gs}px!important;min-height:0!important;'
            'overflow-x:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;'
            'scrollbar-gutter:stable!important;box-sizing:border-box!important;}}'
            'html body .gdrs-summary-table-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;}'
            '</style></head>',
            1,
        )
        components.html(doc_sc, height=_h_gs, scrolling=False)
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
            _pad_h = 18
        elif _wide_tbl:
            _pad_h = 18
        elif "gdrs-summary-table-wrap" in (html or ""):
            _pad_h = 28
        else:
            _pad_h = 10
        components.html(
            doc,
            height=max(68 if (_covenant_tbl or _pd_tbl) else 96, _h_compact + _pad_h),
            scrolling=False,
        )
        return
    _h = _estimate_html_block_height(html)
    if "pred-detail-wrap" not in (html or "") and "exec-doc-scroll-wrap" not in (html or "") and "fc-table-scroll-wrap" not in (html or "") and "gdrs-matrix-table" not in (html or ""):
        _h = min(900, max(320, int(_h)))
    _no_iframe_scroll = (
        "gdrs-summary-table-wrap",
        "budget-deviation-table-wrap",
        "pf-dates-table-wrap",
        "pred-detail-wrap",
        "exec-doc-scroll-wrap",
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
