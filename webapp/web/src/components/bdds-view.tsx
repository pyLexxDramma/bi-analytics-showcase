"use client";

import { FinancePeriodView } from "@/components/finance-period-view";
import { fetchBdds } from "@/lib/api";

export function BddsView() {
  return (
    <FinancePeriodView
      title="БДДС (расходы)"
      subtitle="План и факт расходов по оборотам 1С (ТипСтатьи = БДДС)"
      fetchPayload={fetchBdds}
    />
  );
}
