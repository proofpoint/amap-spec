/*
 * AMAP document validator: a line-for-line port of fixtures/validate.py
 * from the amap-spec repository, for use in the browser (and in Node, for
 * the fixture test in tools/test_validator.mjs).
 *
 * The schemas and the example documents are NOT fetched at runtime (the page
 * must work from file://). They are embedded in assets/validator-schemas.js,
 * which is generated from the spec checkout. Regenerate it after any schema or
 * fixture change:
 *
 *     node tools/gen_validator_schemas.mjs     # writes assets/validator-schemas.js
 *     node tools/test_validator.mjs            # every fixture must behave as in validate.py
 *
 * Porting notes (where JavaScript differs from Python and validate.py's actual
 * behaviour is reproduced on purpose):
 *   - JSON is parsed by a small parser of our own rather than JSON.parse, so
 *     that (a) integer and float literals stay distinguishable ("type":
 *     "integer" rejects 1.0 in Python, where json.loads returns a float),
 *     (b) NaN / Infinity / -Infinity are accepted, as Python's json.loads
 *     accepts them, (c) raw control characters inside strings are rejected,
 *     as json.loads(strict=True) does, and (d) object key order is kept and
 *     a key such as "__proto__" is an ordinary key. Objects become Map, and
 *     numbers become Num {v, isFloat}.
 *   - Equality for const / enum / index uses Python's == semantics: True == 1,
 *     False == 0, 1 == 1.0, and deep comparison of lists and dicts.
 *   - minLength counts code points, as Python's len() does on str (JavaScript's
 *     .length counts UTF-16 units).
 *   - pattern: validate.py rewrites a trailing "$" to "\Z" because Python's
 *     "$" also matches before a final "\n". A JavaScript RegExp without the m
 *     flag already treats "$" as true end of input, so the schema pattern is
 *     used unchanged and re.search() maps to RegExp.test(). Every shipped
 *     pattern also carries "(?!\n)" before "$" itself (see validate.py's
 *     "v3.0.0 note on pattern").
 *   - The content_ref post-check formats notice_id with Python str() rules
 *     (None -> "None", True -> "True", 1.0 -> "1.0") before comparing.
 *
 * Nothing here sends data anywhere. Everything runs locally.
 */
(function (root) {
  "use strict";

  // ---- filename prefix -> schema, exactly as validate.py's SCHEMA_FOR_PREFIX
  var SCHEMA_FOR_PREFIX = [
    ["directory-", "directory.schema.json"],
    ["roster-", "roster.schema.json"],
    ["notice-", "deliver-notice.schema.json"],
    ["request-", "submit-request.schema.json"],
    ["result-", "result.schema.json"],
    ["identity-", "binding-record.schema.json"],
    ["message-", "inbound-message.schema.json"],
    ["peer-", "peer-notice.schema.json"],
  ];

  function Num(v, isFloat, raw) { this.v = v; this.isFloat = isFloat; this.raw = raw; }

  // ---- a strict JSON parser mirroring Python's json.loads --------------------
  function ParseError(msg, pos) { this.message = msg; this.pos = pos; }

  function parseJSON(text) {
    var i = 0, n = text.length;
    function err(msg) { throw new ParseError(msg, i); }
    function ws() { while (i < n) { var c = text[i]; if (c === " " || c === "\t" || c === "\n" || c === "\r") i++; else break; } }
    function value() {
      ws();
      if (i >= n) err("Expecting value");
      var c = text[i];
      if (c === "{") return object();
      if (c === "[") return array();
      if (c === '"') return string();
      if (text.startsWith("true", i)) { i += 4; return true; }
      if (text.startsWith("false", i)) { i += 5; return false; }
      if (text.startsWith("null", i)) { i += 4; return null; }
      if (text.startsWith("NaN", i)) { i += 3; return new Num(NaN, true, "NaN"); }
      if (text.startsWith("Infinity", i)) { i += 8; return new Num(Infinity, true, "Infinity"); }
      if (text.startsWith("-Infinity", i)) { i += 9; return new Num(-Infinity, true, "-Infinity"); }
      return number();
    }
    function number() {
      var m = /^-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/.exec(text.slice(i));
      if (!m || m[0] === "" || m[0] === "-") err("Expecting value");
      i += m[0].length;
      var isFloat = !!(m[1] || m[2]);
      return new Num(Number(m[0]), isFloat, m[0]);
    }
    function string() {
      i++; // opening quote
      var out = "";
      while (true) {
        if (i >= n) err("Unterminated string");
        var c = text[i];
        if (c === '"') { i++; return out; }
        if (c === "\\") {
          i++;
          var e = text[i];
          var map = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
          if (e in map) { out += map[e]; i++; continue; }
          if (e === "u") {
            var hex = text.substr(i + 1, 4);
            if (!/^[0-9a-fA-F]{4}$/.test(hex)) err("Invalid \\uXXXX escape");
            out += String.fromCharCode(parseInt(hex, 16));
            i += 5;
            continue;
          }
          err("Invalid \\escape");
        }
        if (c.charCodeAt(0) < 0x20) err("Invalid control character in string");
        out += c; i++;
      }
    }
    function array() {
      i++; var arr = []; ws();
      if (text[i] === "]") { i++; return arr; }
      while (true) {
        arr.push(value()); ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "]") { i++; return arr; }
        err("Expecting ',' delimiter");
      }
    }
    function object() {
      i++; var obj = new Map(); ws();
      if (text[i] === "}") { i++; return obj; }
      while (true) {
        ws();
        if (text[i] !== '"') err("Expecting property name enclosed in double quotes");
        var k = string(); ws();
        if (text[i] !== ":") err("Expecting ':' delimiter");
        i++;
        var v = value();
        if (obj.has(k)) obj.delete(k); // Python: a repeated key replaces the value in place
        obj.set(k, v);
        ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "}") { i++; return obj; }
        err("Expecting ',' delimiter");
      }
    }
    var result = value(); ws();
    if (i !== n) err("Extra data");
    return result;
  }

  // ---- Python-flavoured helpers ----------------------------------------------
  function isObj(x) { return x instanceof Map; }
  function isNum(x) { return x instanceof Num; }
  function numeric(x) { // value as a Python number, or undefined
    if (typeof x === "boolean") return x ? 1 : 0;
    if (isNum(x)) return x.v;
    return undefined;
  }
  function pyEq(a, b) { // a, b: parsed values or schema (plain JS) values
    a = fromSchema(a); b = fromSchema(b);
    var na = numeric(a), nb = numeric(b);
    if (na !== undefined || nb !== undefined) return na !== undefined && nb !== undefined && na === nb;
    if (typeof a === "string" || typeof b === "string") return a === b;
    if (a === null || b === null) return a === b;
    if (Array.isArray(a) || Array.isArray(b)) {
      if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
      for (var i = 0; i < a.length; i++) if (!pyEq(a[i], b[i])) return false;
      return true;
    }
    if (isObj(a) && isObj(b)) {
      if (a.size !== b.size) return false;
      var ok = true;
      a.forEach(function (v, k) { if (!b.has(k) || !pyEq(v, b.get(k))) ok = false; });
      return ok;
    }
    return false;
  }
  // schema values are plain JSON.parse output; lift them into the document representation
  function fromSchema(x) {
    if (x instanceof Num || x instanceof Map) return x;
    if (typeof x === "number") return new Num(x, !Number.isInteger(x), String(x));
    if (Array.isArray(x)) return x.map(fromSchema);
    if (x && typeof x === "object") {
      var m = new Map();
      Object.keys(x).forEach(function (k) { m.set(k, fromSchema(x[k])); });
      return m;
    }
    return x;
  }
  function pyFloatRepr(v) {
    if (Number.isNaN(v)) return "nan";
    if (v === Infinity) return "inf";
    if (v === -Infinity) return "-inf";
    if (Number.isInteger(v) && Math.abs(v) < 1e16) return v.toFixed(1);
    return String(v); // close to Python's repr; only ever used in error text
  }
  function pyRepr(x) {
    if (x === null || x === undefined) return "None";
    if (x === true) return "True";
    if (x === false) return "False";
    if (isNum(x)) return x.isFloat ? pyFloatRepr(x.v) : x.raw;
    if (typeof x === "number") return pyRepr(fromSchema(x));
    if (typeof x === "string") {
      var q = x.indexOf("'") >= 0 && x.indexOf('"') < 0 ? '"' : "'";
      var body = "";
      for (var ch of x) {
        var c = ch.codePointAt(0);
        if (ch === "\\") body += "\\\\";
        else if (ch === q) body += "\\" + q;
        else if (ch === "\n") body += "\\n";
        else if (ch === "\r") body += "\\r";
        else if (ch === "\t") body += "\\t";
        else if (c < 0x20 || c === 0x7f) body += "\\x" + c.toString(16).padStart(2, "0");
        else body += ch;
      }
      return q + body + q;
    }
    if (Array.isArray(x)) return "[" + x.map(pyRepr).join(", ") + "]";
    if (isObj(x)) {
      var parts = [];
      x.forEach(function (v, k) { parts.push(pyRepr(k) + ": " + pyRepr(v)); });
      return "{" + parts.join(", ") + "}";
    }
    if (typeof x === "object") return pyRepr(fromSchema(x));
    return String(x);
  }
  function pyStr(x) { return typeof x === "string" ? x : pyRepr(x); }
  function pyTypeName(x) {
    if (x === null) return "NoneType";
    if (typeof x === "boolean") return "bool";
    if (isNum(x)) return x.isFloat ? "float" : "int";
    if (typeof x === "string") return "str";
    if (Array.isArray(x)) return "list";
    if (isObj(x)) return "dict";
    return typeof x;
  }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  function typeOk(value, spec) {
    var types = Array.isArray(spec) ? spec : [spec];
    for (var t = 0; t < types.length; t++) {
      var ty = types[t];
      if (ty === "object" && isObj(value)) return true;
      if (ty === "array" && Array.isArray(value)) return true;
      if (ty === "string" && typeof value === "string") return true;
      if (ty === "boolean" && typeof value === "boolean") return true;
      if (ty === "null" && value === null) return true;
      if (ty === "number" && isNum(value)) return true; // bool excluded, as in _type_ok
      if (ty === "integer" && isNum(value) && !value.isFloat) return true;
    }
    return false;
  }
  function specRepr(spec) { return Array.isArray(spec) ? pyRepr(spec) : spec; }

  var patternCache = Object.create(null);
  function pattern(p) {
    if (!(p in patternCache)) patternCache[p] = new RegExp(p);
    return patternCache[p];
  }

  // ---- validate(), mirroring validate.py -----------------------------------
  function validate(value, schema, path, errs) {
    path = path || "$";
    errs = errs || [];

    if (has(schema, "const") && !pyEq(value, schema.const))
      errs.push(path + ": " + pyRepr(value) + " != const " + pyRepr(schema.const));
    if (has(schema, "enum") && !schema.enum.some(function (e) { return pyEq(value, e); }))
      errs.push(path + ": " + pyRepr(value) + " not in enum " + pyRepr(schema.enum));
    if (has(schema, "type") && !typeOk(value, schema.type)) {
      errs.push(path + ": type " + pyTypeName(value) + " != " + specRepr(schema.type));
      return errs; // further checks assume the type held
    }

    if (typeof value === "string") {
      if (has(schema, "minLength") && Array.from(value).length < schema.minLength)
        errs.push(path + ": shorter than minLength " + schema.minLength);
      if (has(schema, "pattern") && !pattern(schema.pattern).test(value))
        errs.push(path + ": " + pyRepr(value) + " fails pattern " + schema.pattern);
    }

    if (isNum(value)) {
      if (has(schema, "minimum") && value.v < schema.minimum)
        errs.push(path + ": " + pyRepr(value) + " below minimum " + pyRepr(schema.minimum));
    }

    if (Array.isArray(value)) {
      if (has(schema, "minItems") && value.length < schema.minItems)
        errs.push(path + ": fewer than minItems " + schema.minItems);
      if (has(schema, "items"))
        value.forEach(function (item, i) { validate(item, schema.items, path + "[" + i + "]", errs); });
    }

    if (isObj(value)) {
      (schema.required || []).forEach(function (req) {
        if (!value.has(req)) errs.push(path + ": missing required '" + req + "'");
      });
      var props = has(schema, "properties") ? schema.properties : {};
      if (schema.additionalProperties === false) {
        value.forEach(function (_, k) {
          if (!has(props, k)) errs.push(path + ": additional property '" + k + "' not allowed");
        });
      }
      value.forEach(function (v, k) {
        if (has(props, k)) validate(v, props[k], path + "." + k, errs);
      });
    }

    (schema.allOf || []).forEach(function (sub) { validate(value, sub, path, errs); });

    if (has(schema, "if") && has(schema, "then")) {
      var scratch = [];
      validate(value, schema["if"], path, scratch);
      if (scratch.length === 0) validate(value, schema.then, path, errs);
    }
    return errs;
  }

  function checkResultAttachmentIndexBinding(doc) {
    var errs = [];
    var atts = isObj(doc) ? doc.get("attachments") : undefined;
    if (!Array.isArray(atts)) return errs;
    atts.forEach(function (item, i) {
      if (!isObj(item)) return;
      var idx = item.get("index");
      if (!pyEq(idx === undefined ? null : idx, new Num(i, false, String(i))))
        errs.push("$.attachments[" + i + "]: index " + pyRepr(idx) + " != array position " + i);
    });
    return errs;
  }

  function checkContentRefIndexBinding(doc) {
    var errs = [];
    if (!isObj(doc)) return errs;
    var noticeId = doc.has("notice_id") ? doc.get("notice_id") : null;
    var message = doc.get("message");
    var atts = isObj(message) ? message.get("attachments") : doc.get("attachments");
    if (!Array.isArray(atts)) return errs;
    atts.forEach(function (item, i) {
      if (!isObj(item) || !item.has("content_ref")) return;
      var want = pyStr(noticeId) + ".attachments/" + i;
      var got = item.get("content_ref");
      if (!(typeof got === "string" && got === want))
        errs.push("$.attachments[" + i + "].content_ref: " + pyRepr(got) + " != " + pyRepr(want));
    });
    return errs;
  }

  function schemaFor(name, schemas) {
    for (var k = 0; k < SCHEMA_FOR_PREFIX.length; k++)
      if (name.indexOf(SCHEMA_FOR_PREFIX[k][0]) === 0) return schemas[SCHEMA_FOR_PREFIX[k][1]];
    throw new Error("no schema mapping for fixture '" + name + "'");
  }

  // name: a fixture filename, or just the prefix ("request-") the page selects
  function checkDocument(name, doc, schemas) {
    var errs = validate(doc, schemaFor(name, schemas));
    if (name.indexOf("result-") === 0) errs = errs.concat(checkResultAttachmentIndexBinding(doc));
    if (/^(notice-|message-|peer-)/.test(name)) errs = errs.concat(checkContentRefIndexBinding(doc));
    return errs;
  }

  var api = { parseJSON: parseJSON, ParseError: ParseError, checkDocument: checkDocument,
              validate: validate, SCHEMA_FOR_PREFIX: SCHEMA_FOR_PREFIX };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.AMAPValidator = api;

  // ---- page wiring (browser only) ------------------------------------------
  if (typeof document === "undefined") return;
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }

  function run() {
    var out = $("v-result");
    out.innerHTML = "";
    var prefix = $("v-type").value;
    var text = $("v-input").value;
    var box;
    if (!text.trim()) { box = el("div", "result fail"); box.appendChild(el("strong", "", "Paste or load a document first.")); out.appendChild(box); return; }
    var doc;
    try { doc = parseJSON(text); }
    catch (e) {
      box = el("div", "result fail");
      box.appendChild(el("strong", "", "Not valid JSON."));
      box.appendChild(el("p", "", e.message + (e.pos !== undefined ? " (character " + e.pos + ")" : "")));
      out.appendChild(box); return;
    }
    var errs = checkDocument(prefix, doc, root.AMAP_SCHEMAS);
    box = el("div", "result " + (errs.length ? "fail" : "ok"));
    var label = $("v-type").selectedOptions[0].textContent;
    box.appendChild(el("strong", "", errs.length
      ? "Fails the " + label + " schema (" + errs.length + " error" + (errs.length > 1 ? "s" : "") + ")."
      : "Passes the " + label + " schema and its post-checks."));
    if (errs.length) {
      var ul = el("ul");
      errs.forEach(function (e) { ul.appendChild(el("li", "", e)); });
      box.appendChild(ul);
    } else {
      box.appendChild(el("p", "small", "A pass is necessary, not sufficient: conformance also needs the operational checks listed below."));
    }
    out.appendChild(box);
  }

  function init() {
    if (!$("v-run")) return;
    $("v-run").addEventListener("click", run);
    $("v-file").addEventListener("change", function (ev) {
      var f = ev.target.files && ev.target.files[0];
      if (!f) return;
      var r = new FileReader();
      r.onload = function () { $("v-input").value = r.result; $("v-result").innerHTML = ""; };
      r.readAsText(f);
    });
    var ex = $("v-example");
    (root.AMAP_EXAMPLES || []).forEach(function (x, i) {
      var o = el("option", "", (x.valid ? "Valid: " : "Invalid: ") + x.name);
      o.value = String(i);
      ex.appendChild(o);
    });
    ex.addEventListener("change", function () {
      var x = root.AMAP_EXAMPLES[Number(ex.value)];
      if (!x) return;
      $("v-input").value = x.text;
      var prefix = x.name.slice(0, x.name.indexOf("-") + 1);
      $("v-type").value = prefix;
      $("v-result").innerHTML = "";
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})(typeof window !== "undefined" ? window : globalThis);
