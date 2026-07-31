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
      <Card className="rounded-xl">
        <Text>Пользователь</Text>
        <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
          {username || "—"}
        </Metric>
      </Card>
      <Card className="rounded-xl">
        <Text>Роль</Text>
        <Metric className="mt-2 text-emerald-700 dark:text-emerald-300">
          {roleLabel || "—"}
        </Metric>
      </Card>
    </Grid>
  );
}
