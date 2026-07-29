"use client";

/** Animated construction + analytics backdrop for the login screen. */
export function ConstructionAnalyticsScene() {
  return (
    <div className="login-scene pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <div className="login-sky" />
      <div className="login-grid" />

      <svg className="login-crane" viewBox="0 0 420 320" fill="none">
        <g className="crane-tower">
          <rect x="188" y="110" width="18" height="190" fill="#1e3a5f" />
          <rect x="170" y="290" width="54" height="12" rx="2" fill="#0f2744" />
          <path d="M197 110 L197 40 L320 40" stroke="#f59e0b" strokeWidth="6" strokeLinecap="round" />
          <circle cx="197" cy="40" r="8" fill="#fb923c" />
        </g>
        <g className="crane-hook">
          <line x1="300" y1="40" x2="300" y2="120" stroke="#94a3b8" strokeWidth="2" strokeDasharray="4 3" />
          <rect x="286" y="120" width="28" height="18" rx="3" fill="#14b8a6" />
          <text x="300" y="133" textAnchor="middle" fontSize="9" fill="#042f2e" fontWeight="700">
            KPI
          </text>
        </g>
      </svg>

      <div className="login-skyline">
        {[42, 68, 54, 88, 60, 76, 48, 92, 58].map((h, i) => (
          <span key={i} style={{ height: `${h}%`, animationDelay: `${i * 0.18}s` }} />
        ))}
      </div>

      <div className="login-chart login-chart-a">
        <div className="bars">
          {[40, 62, 48, 78, 55, 88, 70].map((h, i) => (
            <i key={i} style={{ height: `${h}%`, animationDelay: `${0.2 + i * 0.12}s` }} />
          ))}
        </div>
        <em>БДДС · план/факт</em>
      </div>

      <div className="login-chart login-chart-b">
        <svg viewBox="0 0 120 70" className="spark">
          <path
            className="spark-line"
            d="M4 55 C20 50, 28 20, 42 28 S62 62, 78 35 S100 10, 116 18"
            fill="none"
            stroke="#38bdf8"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </svg>
        <em>Сроки · отклонение</em>
      </div>

      <div className="login-chip login-chip-1">ГПЗУ ✓</div>
      <div className="login-chip login-chip-2">РС +12 дн.</div>
      <div className="login-chip login-chip-3">ГДРС live</div>
      <div className="login-ring" />
      <div className="login-dust">
        {Array.from({ length: 18 }).map((_, i) => (
          <span key={i} style={{ left: `${6 + i * 5}%`, animationDelay: `${i * 0.35}s` }} />
        ))}
      </div>
    </div>
  );
}
