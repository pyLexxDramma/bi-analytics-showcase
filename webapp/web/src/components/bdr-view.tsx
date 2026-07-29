"use client";

import { FinancePeriodView } from "@/components/finance-period-view";
import { fetchBdr } from "@/lib/api";

export function BdrView() {
  return (
    <FinancePeriodView
      title="БДР (расходы)"
      subtitle="План и факт расходов по оборотам 1С (ТипСтатьи = БДР)"
      fetchPayload={fetchBdr}
    />
  );
}
