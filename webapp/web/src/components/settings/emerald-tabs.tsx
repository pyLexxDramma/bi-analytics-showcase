"use client";

export function EmeraldTabs({
  tabs,
  active,
  onChange,
  className = "",
}: {
  tabs: Array<{ id: string; label: string }>;
  active: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={`border-b border-gray-200 dark:border-dark-tremor-border ${className}`}>
      <div className="flex flex-wrap gap-1">
        {tabs.map((tab) => {
          const isActive = tab.id === active;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onChange(tab.id)}
              className={`relative px-4 py-2.5 text-sm font-medium transition ${
                isActive
                  ? "text-emerald-800 dark:text-emerald-300"
                  : "text-gray-600 hover:text-gray-900 dark:text-dark-tremor-content dark:hover:text-dark-tremor-content-strong"
              }`}
            >
              {tab.label}
              {isActive ? (
                <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-emerald-500" />
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
