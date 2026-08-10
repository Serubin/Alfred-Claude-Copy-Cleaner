#!/usr/bin/env node
// Regenerates tests/reference.mjs: the original cleaning routine from
// trevorfox.com's Claude Code Paste Cleaner, carved out of its shipped JS bundle so
// the Python port can be diffed against it.
//
//   node tools/extract_reference.mjs <chunk.js>
//   node tools/extract_reference.mjs https://trevorfox.com/_next/static/chunks/<hash>.js
//
// The cleaner lives in a lazy-loaded chunk, not the page HTML. To find the current
// one: fetch the tool page, collect every /_next/static/chunks/*.js it names, fetch
// those, and grep for "box drawing" — the chunk that matches is the one to pass here.
// The chunk hash changes on every deploy, which is why the generated file is checked
// in rather than fetched at test time.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "tests", "reference.mjs");

const source = process.argv[2];
if (!source) {
  console.error("usage: node tools/extract_reference.mjs <chunk.js|url>");
  process.exit(2);
}

const chunk = source.startsWith("http")
  ? await (await fetch(source)).text()
  : fs.readFileSync(source, "utf8");

// The chunk is a minified webpack/turbopack module. Three landmarks bound the part we
// want: the rule table, the end of the pure helpers, and the cleaning closure itself.
const preludeStart = chunk.indexOf('let r=["plain","markdown"]');
const preludeEnd = chunk.indexOf("var I=e.i(30734)");
const fnStart = chunk.indexOf("(function(e,t,s){");
const fnEnd = chunk.indexOf("})(L,l,H)", fnStart);

if (preludeStart < 0 || preludeEnd < 0 || fnStart < 0 || fnEnd < 0) {
  console.error(
    "could not locate the cleaner in this chunk — the site's bundle has changed " +
      "shape and the landmarks in this script need updating"
  );
  process.exit(1);
}

const prelude = chunk.slice(preludeStart, preludeEnd);
const cleanFn = chunk.slice(fnStart + 1, fnEnd + 1);

const header = `// AUTO-EXTRACTED REFERENCE IMPLEMENTATION -- TEST FIXTURE ONLY, DO NOT EDIT.
//
// Source: ${source}
// The minified cleaning routine from trevorfox.com's Claude Code Paste Cleaner,
// carved out verbatim (React and analytics code removed) so that the Python port in
// src/clean_claude_text.py can be diffed against the real thing byte-for-byte.
// Regenerate with: node tools/extract_reference.mjs <chunk.js|url>

import fs from "node:fs";

`;

const footer = `

export const RULES = a;
export const defaultRules = o;
export const clean = ${cleanFn};

// CLI: plain stdin -> stdout, or --batch for NUL-separated cases in and out, which
// keeps the differential test to a single node process instead of thousands.
if (import.meta.url === \`file://\${process.argv[1]}\`) {
  const mode = process.argv[2] === "markdown" ? "markdown" : "plain";
  const rules = o(mode);
  const input = fs.readFileSync(0, "utf8");
  if (process.argv.includes("--batch")) {
    const out = input.split("\\u0000").map((c) => clean(c, mode, rules).output);
    process.stdout.write(out.join("\\u0000"));
  } else {
    process.stdout.write(clean(input, mode, rules).output);
  }
}
`;

fs.writeFileSync(OUT, header + prelude + footer);
console.log(`wrote ${path.relative(ROOT, OUT)} (${header.length + prelude.length + footer.length} bytes)`);
