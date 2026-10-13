// Run every amap-spec fixture through the browser validator (assets/validator.js)
// and confirm it agrees with fixtures/validate.py: valid/ passes, invalid/ fails.
//
//     node tools/test_validator.mjs [path-to-amap-spec]
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const site = resolve(here, "..");
const spec = resolve(process.argv[2] || join(site, ".."));

const require = createRequire(import.meta.url);
const V = require(join(site, "assets", "validator.js"));
const ctx = {};
vm.runInNewContext(readFileSync(join(site, "assets", "validator-schemas.js"), "utf8"), { globalThis: ctx, window: ctx });
const schemas = ctx.AMAP_SCHEMAS;

let checked = 0;
const bad = [];
for (const [want, sub] of [[true, "valid"], [false, "invalid"]]) {
  for (const f of readdirSync(join(spec, "fixtures", sub)).filter((f) => f.endsWith(".json")).sort()) {
    checked++;
    let errs;
    try {
      errs = V.checkDocument(f, V.parseJSON(readFileSync(join(spec, "fixtures", sub, f), "utf8")), schemas);
    } catch (e) {
      errs = ["parse error: " + e.message];
    }
    const passed = errs.length === 0;
    if (passed !== want) bad.push(`[${sub}] ${f} ${want ? "should PASS but failed: " + JSON.stringify(errs) : "should FAIL but passed"}`);
  }
}
console.log(`browser validator: ${checked} fixtures checked, ${bad.length} unexpected.`);
bad.forEach((b) => console.log("  FAIL:", b));

// the reference: validate.py must say the same
const py = execFileSync("python3", [join(spec, "fixtures", "validate.py")], { encoding: "utf8" });
const m = py.match(/(\d+) fixtures checked, (\d+) unexpected\./);
console.log(`validate.py:        ${m ? m[1] + " fixtures checked, " + m[2] + " unexpected." : "(no summary line found)"}`);
const agree = m && Number(m[1]) === checked && Number(m[2]) === 0 && bad.length === 0;
console.log(agree ? "AGREE" : "DISAGREE");
process.exit(agree ? 0 : 1);
