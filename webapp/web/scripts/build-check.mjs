import { spawnSync } from "node:child_process";

// Keep verify builds out of `.next` so a parallel `npm run dev` stays intact.
process.env.NEXT_DIST_DIR = ".next-check";

const result = spawnSync("npx", ["next", "build"], {
  stdio: "inherit",
  env: process.env,
  shell: true,
});

process.exit(result.status ?? 1);
