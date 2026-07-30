"use client";

import { BddsView } from "@/components/bdds-view";
import { fetchBdr } from "@/lib/api";

export function BdrView() {
  return (
    <BddsView
      config={{
        title: "БДР (расходы)",
        planSeries: "План расходов",
        factSeries: "Факт расходов",
        sheetName: "БДР",
        fetchPayload: fetchBdr,
      }}
    />
  );
}
