"use client";

/** Единая подсказка под finance-графиками: подписи в млн ₽. */
export function ChartHint({ children }: { children?: React.ReactNode }) {
  return (
    <p className="bi-chart-hint mt-1 text-center text-xs text-tremor-content dark:text-dark-tremor-content">
      {children ?? "Подписи на столбцах — млн ₽."}
    </p>
  );
}
