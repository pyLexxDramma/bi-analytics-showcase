"""Полноэкранный лоадер с блокировкой экрана на время пересчёта/рендера Streamlit.

Зачем: на тяжёлых отчётах рендер визуальных представлений занимает заметное
время, в течение которого старый контент остаётся кликабельным и создаёт
ощущение «подвисания». Этот модуль навешивает на родительский документ
(через ``components.html`` → ``window.parent.document``) фиксированный overlay
со спиннером и блокировкой кликов, который показывается, пока Streamlit
выполняет скрипт (виден индикатор ``stStatusWidget``), и скрывается сразу
после завершения рендера.

Public API: ``inject_loading_overlay``, ``loading_overlay_enabled``.

По умолчанию включён на всех ветках/деплоях. ``BI_ANALYTICS_LOADING_OVERLAY=0``
отключает. Безопасно: есть аварийный
авто-сброс overlay (если индикатор «завис»), чтобы экран не остался
заблокированным навсегда.
"""

from __future__ import annotations

import os

import streamlit.components.v1 as components


def loading_overlay_enabled() -> bool:
    return os.environ.get("BI_ANALYTICS_LOADING_OVERLAY", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


# Минимальная задержка перед показом (мс): мгновенные rerun не мигают overlay.
_SHOW_AFTER_MS = 280
# Аварийный предел показа (мс): даже если индикатор «завис», экран разблокируется.
_MAX_VISIBLE_MS = 60000

_OVERLAY_JS = """
<script>
(function () {
    try {
        var KEY = '__BI_LOADING_OVERLAY_V2__';
        var SHOW_AFTER_MS = %SHOW_AFTER_MS%;
        var MAX_VISIBLE_MS = %MAX_VISIBLE_MS%;

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
        var win = doc.defaultView || window.parent || window;

        // singleton на вкладку: гасим предыдущий наблюдатель/таймер
        try {
            var prev = win[KEY];
            if (prev) {
                if (prev.obs && prev.obs.disconnect) prev.obs.disconnect();
                if (prev.tmr) clearInterval(prev.tmr);
            }
        } catch (eDisc) {}

        if (!doc.getElementById('bi-loading-overlay-style')) {
            var style = doc.createElement('style');
            style.id = 'bi-loading-overlay-style';
            style.textContent = [
                '#bi-loading-overlay{',
                '  position:fixed;inset:0;z-index:2147483646;',
                '  display:flex;align-items:center;justify-content:center;',
                '  background:rgba(8,12,20,0.55);backdrop-filter:blur(2px);',
                '  -webkit-backdrop-filter:blur(2px);',
                '  opacity:0;visibility:hidden;pointer-events:none;',
                '  transition:opacity .15s ease;}',
                '#bi-loading-overlay.bi-lo-on{opacity:1;visibility:visible;pointer-events:auto;}',
                '#bi-loading-overlay .bi-lo-box{',
                '  display:flex;flex-direction:column;align-items:center;gap:14px;',
                '  padding:26px 34px;border-radius:14px;',
                '  background:rgba(17,24,39,0.92);',
                '  box-shadow:0 10px 40px rgba(0,0,0,0.45);',
                '  border:1px solid rgba(148,163,184,0.25);}',
                '#bi-loading-overlay .bi-lo-spinner{',
                '  width:46px;height:46px;border-radius:50%;',
                '  border:4px solid rgba(148,163,184,0.30);',
                '  border-top-color:#38bdf8;',
                '  animation:bi-lo-spin .8s linear infinite;}',
                '#bi-loading-overlay .bi-lo-text{',
                '  color:#e8eef5;font-size:15px;font-weight:600;',
                '  font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;',
                '  letter-spacing:.2px;}',
                '@keyframes bi-lo-spin{to{transform:rotate(360deg);}}',
                '@media (prefers-reduced-motion:reduce){',
                '  #bi-loading-overlay .bi-lo-spinner{animation-duration:1.6s;}}'
            ].join('');
            (doc.head || doc.body).appendChild(style);
        }

        var ov = doc.getElementById('bi-loading-overlay');
        if (!ov) {
            ov = doc.createElement('div');
            ov.id = 'bi-loading-overlay';
            ov.setAttribute('role', 'status');
            ov.setAttribute('aria-live', 'polite');
            ov.innerHTML =
                '<div class="bi-lo-box">' +
                '<div class="bi-lo-spinner" aria-hidden="true"></div>' +
                '<div class="bi-lo-text">Загрузка отчёта…</div>' +
                '</div>';
            doc.body.appendChild(ov);
        }

        function isVisible(el) {
            if (!el) return false;
            try {
                var cs = win.getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0)
                    return false;
            } catch (e) {}
            return (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
        }

        function statusWidgetBusy() {
            var sw = doc.querySelector('[data-testid="stStatusWidget"]');
            if (!sw || !isVisible(sw)) return false;
            return !!(
                sw.querySelector('svg, img, [data-testid="stStatusWidgetRunningIcon"]') ||
                (sw.textContent || '').trim().length > 0
            );
        }

        function appStatusBusy() {
            var as = doc.querySelector('[data-testid="stAppStatus"]');
            if (!as || !isVisible(as)) return false;
            return !!(
                as.querySelector('svg, img, [data-testid="stStatusWidgetRunningIcon"]') ||
                (as.textContent || '').trim().length > 0
            );
        }

        function headerSpinnerBusy() {
            var hdr = doc.querySelector('[data-testid="stHeader"]');
            if (!hdr) return false;
            var spin = hdr.querySelector('[data-testid="stSpinner"], [data-testid="stStatusWidget"]');
            return spin && isVisible(spin);
        }

        function isBusy() {
            // Только индикаторы выполнения Streamlit в шапке (Running…).
            // st.spinner внутри отчёта НЕ учитываем: иначе overlay дублирует
            // «Загрузка отчёта…» и блокирует экран на всё время тяжёлого рендера
            // (График проекта + «Показать причины отклонений» → зависание вкладки).
            return statusWidgetBusy() || appStatusBusy() || headerSpinnerBusy();
        }

        var busySince = 0;
        var shownAt = 0;
        var tickPending = false;

        function show() {
            if (!ov.classList.contains('bi-lo-on')) {
                ov.classList.add('bi-lo-on');
                shownAt = Date.now();
            }
        }
        function hide() {
            busySince = 0;
            if (ov.classList.contains('bi-lo-on')) ov.classList.remove('bi-lo-on');
        }

        function tick() {
            tickPending = false;
            if (isBusy()) {
                var now = Date.now();
                if (!busySince) busySince = now;
                if (!ov.classList.contains('bi-lo-on')) {
                    if (now - busySince >= SHOW_AFTER_MS) show();
                } else if (now - shownAt > MAX_VISIBLE_MS) {
                    // аварийный сброс — не держим экран заблокированным вечно
                    hide();
                }
            } else {
                hide();
            }
        }

        function scheduleTick() {
            if (tickPending) return;
            tickPending = true;
            try {
                win.requestAnimationFrame(tick);
            } catch (eRaf) {
                tickPending = false;
                tick();
            }
        }

        var obs = null;
        // Без MutationObserver: на тяжёлых отчётах (График проекта) тысячи DOM-изменений
        // в секунду → лавина callback'ов → «Страница не отвечает». Достаточно polling.
        var tmr = setInterval(scheduleTick, 500);
        try { win[KEY] = { obs: obs, tmr: tmr }; } catch (eH) {}
        scheduleTick();
    } catch (e) { /* noop */ }
})();
</script>
"""


def release_loading_overlay() -> None:
    """Скрыть overlay после завершения тяжёлого рендера."""
    if not loading_overlay_enabled():
        return
    components.html(
        """
<script>
(function () {
    try {
        var doc = window.parent && window.parent.document ? window.parent.document : document;
        var ov = doc.getElementById('bi-loading-overlay');
        if (ov) ov.classList.remove('bi-lo-on');
    } catch (e) {}
})();
</script>
""",
        height=0,
    )


def pulse_loading_overlay() -> None:
    """Сразу показать overlay (тяжёлые отчёты: stStatusWidget может не успеть)."""
    if not loading_overlay_enabled():
        return
    components.html(
        """
<script>
(function () {
    try {
        var doc = window.parent && window.parent.document ? window.parent.document : document;
        var ov = doc.getElementById('bi-loading-overlay');
        if (ov) ov.classList.add('bi-lo-on');
    } catch (e) {}
})();
</script>
""",
        height=0,
    )


def inject_loading_overlay() -> None:
    """Навесить overlay на родительский документ (вызывать на каждый rerun)."""
    if not loading_overlay_enabled():
        return
    js = (
        _OVERLAY_JS
        .replace("%SHOW_AFTER_MS%", str(int(_SHOW_AFTER_MS)))
        .replace("%MAX_VISIBLE_MS%", str(int(_MAX_VISIBLE_MS)))
    )
    components.html(js, height=0)
