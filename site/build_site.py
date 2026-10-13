#!/usr/bin/env python3
"""Assemble the AMAP static site.

Each page is a body fragment in src/<name>.html whose first line is a
metadata comment:

    <!-- title: Page title | description: One-sentence summary -->

This script wraps every fragment in the shared header, navigation and footer,
copies assets/ and the published schemas, and writes a self-contained,
relative-linked site to docs/ at the repository root, which GitHub Pages
serves from the main branch. The output needs no build step to host, and it
also works opened from disk.

Counts that would otherwise drift are filled in from the repository at build
time: {{FIXTURES}}, {{FIXTURES_VALID}}, {{FIXTURES_INVALID}} and
{{DOC_TYPES}} (the number of schemas).

    python3 site/build_site.py           build docs/
    python3 site/build_site.py --check   build to a temporary directory and
                                         fail if docs/ differs (for CI)

Standard library only. It also checks that every internal link resolves.
"""
import filecmp
import html
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
SPEC = os.path.abspath(os.path.join(HERE, ".."))  # the amap-spec checkout
OUT = os.path.join(SPEC, "docs")


def counts():
    fx = os.path.join(SPEC, "fixtures")
    valid = len([f for f in os.listdir(os.path.join(fx, "valid")) if f.endswith(".json")])
    invalid = len([f for f in os.listdir(os.path.join(fx, "invalid")) if f.endswith(".json")])
    schemas = len([f for f in os.listdir(os.path.join(SPEC, "schemas")) if f.endswith(".schema.json")])
    return {"{{FIXTURES}}": str(valid + invalid), "{{FIXTURES_VALID}}": str(valid),
            "{{FIXTURES_INVALID}}": str(invalid), "{{DOC_TYPES}}": str(schemas)}

NAV = [
    ("index.html", "Home"),
    ("ietf.html", "At the IETF"),
    ("why.html", "Why AMAP"),
    ("how-it-works.html", "How it works"),
    ("identity.html", "Identity"),
    ("implementers.html", "Implementers"),
    ("validator.html", "Validator"),
    ("status.html", "Status"),
    ("faq.html", "FAQ"),
    ("get-involved.html", "Get involved"),
]
FOOTER_LINKS = [
    ("layers.html", "MCP, A2A and AMAP"),
    ("glossary.html", "Glossary"),
    ("https://github.com/proofpoint/amap-spec", "Specification on GitHub"),
]

META = re.compile(r"^<!--\s*title:\s*(.*?)\s*\|\s*description:\s*(.*?)\s*-->")

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="icon" href="assets/mark.svg" type="image/svg+xml">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap header-row">
    <a class="brand" href="index.html" aria-label="AMAP home">
      <img src="assets/mark.svg" alt="" width="28" height="28">
      <span class="brand-name">AMAP</span>
      <span class="brand-sub">Agent Mailbox Access Protocol</span>
    </a>
    <button class="nav-toggle" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav id="site-nav" class="site-nav" aria-label="Main">
      <ul>{nav}</ul>
    </nav>
  </div>
</header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site-footer">
  <div class="wrap footer-row">
    <p>AMAP is an open specification, published under the Apache License 2.0. It was originated by Proofpoint and is open to every implementer.</p>
    <ul class="footer-links">{footer}</ul>
  </div>
</footer>
<script src="assets/site.js"></script>
</body>
</html>
"""


# Light-theme colours for the diagram classes. They are written as SVG
# presentation attributes, so any renderer that ignores CSS inside SVG still
# draws the diagram. In a browser the class rules in style.css win, which
# keeps dark mode working.
SVG_FILL = {"d-ink": "#1b2430", "d-muted": "#5b6573", "d-trust": "#0f5c63", "d-trust-bg": "#e3f0f0",
            "d-agent": "#8a5a12", "d-agent-bg": "#fbf1e1", "d-human": "#5b3f86", "d-human-bg": "#eee8f6",
            "d-panel": "#f3f5f8", "d-bg": "#ffffff"}
SVG_STROKE = {"s-rule": "#d5dae1", "s-ink": "#1b2430", "s-trust": "#0f5c63", "s-agent": "#8a5a12",
              "s-human": "#5b3f86", "s-muted": "#5b6573"}


def svg_fallbacks(body):
    def fix(m):
        tag = m.group(0)
        classes = re.search(r'class="([^"]*)"', tag)
        if not classes:
            return tag
        names = classes.group(1).split()
        add = ""
        if " fill=" not in tag:
            fill = next((SVG_FILL[n] for n in names if n in SVG_FILL), None)
            if fill:
                add += f' fill="{fill}"'
        if " stroke=" not in tag:
            stroke = next((SVG_STROKE[n] for n in names if n in SVG_STROKE), None)
            if stroke:
                add += f' stroke="{stroke}"'
        return tag[:-1] + add + ">" if not tag.endswith("/>") else tag[:-2] + add + "/>"
    return re.sub(r"<(?:rect|line|polygon|polyline|path|circle|ellipse|text|tspan)\b[^>]*>", fix, body)


def nav_html(current):
    items = []
    for href, label in NAV:
        cur = ' aria-current="page"' if href == current else ""
        items.append(f'<li><a href="{href}"{cur}>{html.escape(label)}</a></li>')
    return "".join(items)


def footer_html():
    return "".join(f'<li><a href="{h}">{html.escape(l)}</a></li>' for h, l in FOOTER_LINKS)


def build(OUT):
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    # GitHub Pages: serve the files as they are, with no Jekyll processing
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    shutil.copytree(os.path.join(HERE, "assets"), os.path.join(OUT, "assets"))
    # the validator loads the published schemas, copied verbatim from the spec
    shutil.copytree(os.path.join(SPEC, "schemas"), os.path.join(OUT, "schemas"))

    pages = sorted(f for f in os.listdir(SRC) if f.endswith(".html"))
    problems = []
    subs = counts()
    for name in pages:
        raw = open(os.path.join(SRC, name), encoding="utf-8").read()
        m = META.match(raw)
        if not m:
            problems.append(f"{name}: missing metadata comment on line 1")
            continue
        title, desc = m.group(1), m.group(2)
        for k, v in subs.items():
            raw = raw.replace(k, v)
        if "{{" in raw:
            problems.append(f"{name}: unfilled placeholder {re.search(r'{{[^}]*}}', raw).group(0)}")
        full_title = "AMAP" if name == "index.html" else f"{title} · AMAP"
        out = PAGE.format(title=html.escape(full_title), description=html.escape(desc),
                          nav=nav_html(name), footer=footer_html(),
                          body=svg_fallbacks(raw[m.end():].strip()))
        open(os.path.join(OUT, name), "w", encoding="utf-8").write(out)

    # every internal link and asset must resolve
    for name in os.listdir(OUT):
        if not name.endswith(".html"):
            continue
        text = open(os.path.join(OUT, name), encoding="utf-8").read()
        for ref in re.findall(r'(?:href|src)="([^"#]+)', text):
            if re.match(r"^(https?:|mailto:)", ref):
                continue
            if not os.path.exists(os.path.join(OUT, ref)):
                problems.append(f"{name}: broken link {ref}")
    for href, _ in NAV + FOOTER_LINKS:
        if not href.startswith("http") and not os.path.exists(os.path.join(OUT, href)):
            problems.append(f"navigation: {href} has no page")

    return pages, problems


def same_tree(a, b):
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(same_tree(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)


def main():
    if "--check" in sys.argv[1:]:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "docs")
            pages, problems = build(out)
            for p in problems:
                print("PROBLEM:", p)
            if not os.path.isdir(OUT) or not same_tree(out, OUT):
                print("PROBLEM: docs/ differs from what site/ builds. docs/ is generated: "
                      "edit site/ and run python3 site/build_site.py")
                return 1
            print(f"site: {len(pages)} pages, docs/ matches site/")
            return 1 if problems else 0
    pages, problems = build(OUT)
    for p in problems:
        print("PROBLEM:", p)
    print(f"{len(pages)} pages -> {os.path.relpath(OUT, SPEC)}/")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
