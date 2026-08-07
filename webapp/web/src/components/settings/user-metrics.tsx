"use client";

import { Card, Grid, Metric, Text } from "@tremor/react";

export function UserMetrics({
  username,
  roleLabel,
}: {
  username: string;
  roleLabel: string;
}) {
  return (
    <Grid numItemsSm={2} className="mb-6 gap-6">
      <Card className="min-w-0 rounded-xl">
        <Text>Пользователь</Text>
        <Metric className="mt-2 !text-xl !leading-snug break-words [overflow-wrap:anywhere] text-tremor-content-strong dark:!text-dark-tremor-content-strong sm:!text-2xl">
          {username || "—"}
        </Metric>
      </Card>
      <Card className="min-w-0 rounded-xl">
        <Text>Роль</Text>
        <Metric className="mt-2 !text-xl !leading-snug break-words [overflow-wrap:anywhere] text-emerald-700 dark:text-emerald-300 sm:!text-2xl">
          {roleLabel || "—"}
        </Metric>
      </Card>
    </Grid>
  );
}
