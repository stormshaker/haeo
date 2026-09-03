import { mkdir, readdir, unlink } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { build as rolldownBuild, watch as rolldownWatch } from "rolldown";

import rolldownConfig from "../rolldown.config.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, "..");
const workspaceRoot = resolve(rootDir, "..", "..");
const outDir = resolve(workspaceRoot, "custom_components", "haeo", "www");
const forecastOutFile = resolve(outDir, "haeo-forecast-card.min.js");
const topologyCardOutFile = resolve(outDir, "haeo-topology-card.min.js");
const topologyOutFile = resolve(rootDir, "dist", "render-topology-svg.mjs");
const watch = process.argv.includes("--watch");

const CARD_FILE_PREFIXES = ["haeo-forecast-card", "haeo-topology-card"];

async function cleanCardOutputDir() {
  await mkdir(outDir, { recursive: true });
  const entries = await readdir(outDir);
  await Promise.all(
    entries
      .filter((name) => CARD_FILE_PREFIXES.some((prefix) => name.startsWith(prefix)))
      .map((name) => unlink(resolve(outDir, name)))
  );
}

// Entry filenames carry a content hash, so list what was actually emitted.
async function emittedCardFiles() {
  const names = await readdir(outDir);
  return names
    .filter((name) => CARD_FILE_PREFIXES.some((prefix) => name.startsWith(prefix)))
    .sort()
    .map((name) => resolve(outDir, name));
}

if (watch) {
  await cleanCardOutputDir();
  const watcher = await rolldownWatch(rolldownConfig);
  watcher.on("event", (event) => {
    if (event.code === "BUNDLE_END") {
      void emittedCardFiles().then((files) => {
        for (const file of [...files, topologyOutFile]) {
          process.stdout.write(`built ${file}\n`);
        }
      });
    }
    if (event.code === "ERROR") {
      process.stderr.write(`${event.error}\n`);
    }
  });
  process.stdout.write(`watching ${outDir}\n`);
} else {
  await cleanCardOutputDir();
  await rolldownBuild(rolldownConfig);
  for (const file of [...(await emittedCardFiles()), topologyOutFile]) {
    process.stdout.write(`built ${file}\n`);
  }
}
