#!/usr/bin/env node
// One-shot reference extractor — pulls OGA's image-model arrays (t2i + i2i)
// out of `packages/studio/src/models.js` and writes them as JSON for
// future curation work.
//
// Usage:
//   node scripts/extract_oga_catalog.mjs [path-to-OGA] [output-file]
//
// Defaults to the location used during the original audit:
//   K:/Gen Media/Open-Generative-AI
//   ./oga_models_reference.json
//
// NOTE: the live catalog the studio reads is `model_catalog.json`. THIS
// dump is purely for reference when expanding that hand-curated list.

import { writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const ogaRoot = process.argv[2] || "K:/Gen Media/Open-Generative-AI";
const outFile = process.argv[3] || "oga_models_reference.json";
const modelsJsPath = resolve(ogaRoot, "packages/studio/src/models.js");

const mod = await import(pathToFileURL(modelsJsPath).href);
const { t2iModels = [], i2iModels = [] } = mod;

const payload = {
  _source: modelsJsPath,
  _extracted_at: new Date().toISOString(),
  counts: { t2i: t2iModels.length, i2i: i2iModels.length },
  t2i: t2iModels,
  i2i: i2iModels,
};

await writeFile(outFile, JSON.stringify(payload, null, 2), "utf8");
console.log(
  `Wrote ${t2iModels.length} t2i + ${i2iModels.length} i2i entries to ${outFile}`,
);
