// Removes server-only routes so `next build` can export the marketing site as
// static files. CI only (GitHub Pages workflow): it deletes source files.
import { rmSync } from "node:fs";

if (!process.env.CI) {
  console.error("Refusing to run outside CI: this deletes source files.");
  process.exit(1);
}
for (const path of ["src/app/(app)", "src/app/(auth)", "src/app/demo", "src/proxy.ts"]) {
  rmSync(path, { recursive: true, force: true });
  console.log(`removed ${path}`);
}
