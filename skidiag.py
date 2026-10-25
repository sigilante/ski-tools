#!/usr/bin/env python3
"""skidiag: Barendregt-style application-tree diagrams of SKI terms.

    python3 skidiag.py TERMFILE [-o OUTSTEM] [--min-size N] [--fuel N]

TERMFILE holds one term over S, K, I, parentheses and free variables
(lower-case identifiers); application is left-associative and `⬝` is read
as application. `-` reads the term from standard input.

The tool hash-conses the term, names each repeated subterm of at least
--min-size leaves (keeping only names that add sharing), and describes each
named subterm by applying it to fresh variables and reducing. It writes:

    OUTSTEM.txt      legend: sizes, names, definitions, behaviours
    OUTSTEM.svg      ordered application trees, named subterms boxed
    OUTSTEM.pdf      the same, if rsvg-convert is installed
    OUTSTEM.tex      TikZ forest trees, a standalone LaTeX document
    OUTSTEM-dag.svg  the whole term with sharing, if Graphviz is installed

Only the standard library is required.
"""
import argparse
import re
import shutil
import subprocess
import sys
from collections import Counter

sys.setrecursionlimit(100000)

COMBS = ("S", "K", "I")

# ---- terms: an atom is a str, an application is a (fun, arg) tuple ----

def parse(src):
    toks = []
    for m in re.finditer(r"\s+|⬝|[SKI()]|[a-z][A-Za-z0-9_']*|.", src):
        t = m.group()
        if t.isspace() or t == "⬝":
            continue
        if not (t in COMBS or t in "()" or re.fullmatch(r"[a-z][A-Za-z0-9_']*", t)):
            raise SyntaxError(f"unexpected {t!r} at offset {m.start()}")
        toks.append(t)
    pos = 0

    def atom():
        nonlocal pos
        if pos >= len(toks):
            raise SyntaxError("unexpected end of term")
        t = toks[pos]
        pos += 1
        if t == ")":
            raise SyntaxError("unexpected ')'")
        if t == "(":
            e = expr()
            if pos >= len(toks) or toks[pos] != ")":
                raise SyntaxError("missing ')'")
            pos += 1
            return e
        return t

    def expr():
        e = atom()
        while pos < len(toks) and toks[pos] != ")":
            e = (e, atom())
        return e

    e = expr()
    if pos != len(toks):
        raise SyntaxError("unbalanced ')'")
    return e


def hashcons(t, table):
    """Rebuild t so that equal subterms are the same object."""
    if isinstance(t, tuple):
        t = (hashcons(t[0], table), hashcons(t[1], table))
    return table.setdefault(t, t)


def size(t):
    """Number of leaves."""
    n, stack = 0, [t]
    while stack:
        u = stack.pop()
        if isinstance(u, tuple):
            stack.extend(u)
        else:
            n += 1
    return n


def show(t, names=None, top=True, root=None):
    """Concrete syntax; subterms in `names` (by id) print as their name."""
    if names and t is not root and id(t) in names:
        return names[id(t)]
    if not isinstance(t, tuple):
        return t
    s = show(t[0], names, True, root) + " " + show(t[1], names, False, root)
    return s if top else "(" + s + ")"


def spine(t):
    args = []
    while isinstance(t, tuple):
        args.append(t[1])
        t = t[0]
    return t, args[::-1]


def apply(h, args):
    for a in args:
        h = (h, a)
    return h

# ---- leftmost-outermost reduction with fuel ----

class OutOfFuel(Exception):
    pass


def normalize(t, fuel):
    """Normal form of t; `fuel` is a one-element list of remaining steps."""
    while True:
        h, args = spine(t)
        if h == "I" and len(args) >= 1:
            t = apply(args[0], args[1:])
        elif h == "K" and len(args) >= 2:
            t = apply(args[0], args[2:])
        elif h == "S" and len(args) >= 3:
            x, y, z = args[:3]
            t = apply(((x, z), (y, z)), args[3:])
        else:
            return apply(h, [normalize(a, fuel) for a in args])
        fuel[0] -= 1
        if fuel[0] <= 0:
            raise OutOfFuel


def has_comb(t):
    stack = [t]
    while stack:
        u = stack.pop()
        if isinstance(u, tuple):
            stack.extend(u)
        elif u in COMBS:
            return True
    return False


VARS = "abcdefghijkl"


def behaviour(t, max_args, fuel):
    """`λab…. body` for the fewest fresh variables that reduce t to a term
    over the variables alone; None if no such count up to max_args."""
    for n in range(max_args + 1):
        vs = list(VARS[:n])
        try:
            r = normalize(apply(t, vs), [fuel])
        except (OutOfFuel, RecursionError):
            return None
        if not has_comb(r):
            return ("λ" + "".join(vs) + ". " if n else "") + show(r)
    return None


# Standard names, matched on behaviour.
BY_BEHAVIOUR = {
    "λa. a": "I", "λab. a": "K", "λabc. a c (b c)": "S",
    "λabc. a (b c)": "B", "λabc. a c b": "C", "λab. b a": "T",
    "λa. a a": "M", "λab. a b b": "W", "λab. b": "KI",
}
# Standard names for terms with no normal-form behaviour, matched on syntax.
BY_SYNTAX = {
    "S (K (S I I)) (S (S (K S) K) (K (S I I)))": ("Y", "fixed point: Y f = f (Y f)"),
    "S I I (S I I)": ("Ω", "diverges"),
}
RESERVED = set("SKIBCTMWY")

# ---- naming shared subterms ----

def name_shared(t, min_size):
    """Return (names, order): names maps id -> name for the chosen shared
    subterms, order lists them in first-occurrence (pre-order) order."""
    distinct, occ, parents = {}, Counter(), {}

    def walk(u):  # counts tree occurrences; terms are DAGs, so iterate
        stack = [u]
        while stack:
            v = stack.pop()
            occ[id(v)] += 1
            if isinstance(v, tuple):
                if id(v) not in distinct:
                    for c in v:
                        parents.setdefault(id(c), []).append(v)
                distinct[id(v)] = v
                stack.extend(v)
    walk(t)

    cands = {id(u) for u in distinct.values()
             if occ[id(u)] >= 2 and size(u) >= min_size}
    # A candidate whose only occurrence sits once inside another candidate
    # adds a name but no sharing.
    keep = {i for i in cands
            if not (len(parents.get(i, [])) == 1 and id(parents[i][0]) in cands)}

    fresh = iter([chr(c) for c in range(ord("A"), ord("Z") + 1) if chr(c) not in RESERVED]
                 + [f"Z{i}" for i in range(1, 10000)])
    names, order, seen = {}, [], set()
    stack = [t]
    while stack:
        u = stack.pop()
        if not isinstance(u, tuple) or id(u) in seen:
            continue
        seen.add(id(u))
        if id(u) in keep and u is not t:
            names[id(u)] = next(fresh)
            order.append(u)
        stack.extend(reversed(u))
    return names, order

# ---- SVG trees, laid out in leaf order so children never cross ----

DX, DY, R = 22, 34, 8


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def layout(u, names, root):
    """Nodes (x, y, kind, label) and edges; x in leaf units, y in levels."""
    nodes, edges, nxt = [], [], [0]

    def go(v, depth, is_root):
        if not is_root and id(v) in names:
            nodes.append((nxt[0], depth, "box", names[id(v)]))
        elif not isinstance(v, tuple):
            nodes.append((nxt[0], depth, "leaf", v))
        else:
            a = go(v[0], depth + 1, False)
            b = go(v[1], depth + 1, False)
            x = (nodes[a][0] + nodes[b][0]) / 2
            nodes.append((x, depth, "app", "@"))
            edges.append((len(nodes) - 1, a))
            edges.append((len(nodes) - 1, b))
            return len(nodes) - 1
        nxt[0] += 1
        return len(nodes) - 1
    go(u, 0, True)
    return nodes, edges


def svg_trees(blocks, names):
    parts, y0, width = [], 10, 0
    for title, u in blocks:
        nodes, edges = layout(u, names, u)
        w = (max(n[0] for n in nodes) + 1) * DX + 20
        h = (max(n[1] for n in nodes) + 1) * DY + 40
        width = max(width, w)
        g = [f'<g transform="translate(10,{y0})">',
             f'<text x="0" y="14" class="title">{esc(title)}</text>']
        pos = [(10 + n[0] * DX + DX / 2, 40 + n[1] * DY) for n in nodes]
        for a, b in edges:
            (x1, y1), (x2, y2) = pos[a], pos[b]
            g.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')
        for (x, y), (_, _, kind, label) in zip(pos, nodes):
            if kind == "app":
                g.append(f'<circle cx="{x}" cy="{y}" r="{R}"/>'
                         f'<text x="{x}" y="{y + 3.5}" class="at">@</text>')
            elif kind == "box":
                bw = 10 + 7 * len(label)
                g.append(f'<rect x="{x - bw / 2}" y="{y - 10}" width="{bw}" height="20" rx="5"/>'
                         f'<text x="{x}" y="{y + 4.5}" class="name">{esc(label)}</text>')
            else:
                g.append(f'<text x="{x}" y="{y + 4.5}" class="leaf">{esc(label)}</text>')
        g.append("</g>")
        parts.append("\n".join(g))
        y0 += h + 20
    style = ("<style>line{stroke:#333;stroke-width:1}circle{fill:#fff;stroke:#333}"
             "rect{fill:#e8eef7;stroke:#335}text{font-family:Helvetica,Arial,sans-serif;"
             "text-anchor:middle}.title{text-anchor:start;font-weight:bold;font-size:14px}"
             ".at{font-size:9px}.leaf{font-size:13px}.name{font-size:12px;font-weight:bold}"
             "</style>")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + 20}" height="{y0}" '
            f'viewBox="0 0 {width + 20} {y0}"><rect width="100%" height="100%" '
            f'style="fill:#fff;stroke:none"/>{style}\n' + "\n".join(parts) + "\n</svg>\n")

# ---- TikZ forest ----

def forest(u, names, root=True):
    if not root and id(u) in names:
        return "[$\\mathsf{" + names[id(u)] + "}$, draw, rounded corners]"
    if not isinstance(u, tuple):
        return "[$\\mathsf{" + u + "}$]"
    return "[$@$ " + forest(u[0], names, False) + " " + forest(u[1], names, False) + "]"


def tex_doc(blocks, names):
    out = ["\\documentclass[border=6pt,multi=forest]{standalone}",
           "\\usepackage{forest}",
           "\\forestset{ski/.style={for tree={inner sep=1pt, l sep=6pt, s sep=4pt, font=\\small}}}",
           "\\begin{document}"]
    for title, u in blocks:
        out.append(f"% {title}")
        out.append("\\begin{forest} ski " + forest(u, names) + " \\end{forest}")
    out.append("\\end{document}")
    return "\n".join(out) + "\n"

# ---- Graphviz DAG ----

def dot_dag(t):
    lines = ["digraph D {", 'node [fontname="Helvetica", fontsize=10]; edge [arrowsize=0.4];',
             "graph [ordering=out, ranksep=0.25, nodesep=0.1];"]
    ids = {}

    def key(u):
        if id(u) not in ids:
            ids[id(u)] = f"d{len(ids)}"
            if isinstance(u, tuple):
                lines.append(f'{ids[id(u)]} [shape=circle, width=0.22, fixedsize=true, label="@"];')
            else:
                lines.append(f'{ids[id(u)]} [shape=plaintext, label="{u}"];')
        return ids[id(u)]
    done, stack = set(), [t]
    while stack:
        u = stack.pop()
        if not isinstance(u, tuple) or id(u) in done:
            continue
        done.add(id(u))
        lines.append(f'{key(u)} -> {key(u[0])} [color="#3060a0"];')
        lines.append(f'{key(u)} -> {key(u[1])} [color="#a04030"];')
        stack.extend(u)
    key(t)
    lines.append("}")
    return "\n".join(lines) + "\n"

# ---- driver ----

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("term", help="file holding the term, or - for stdin")
    ap.add_argument("-o", "--out", help="output stem (default: the term file's stem)")
    ap.add_argument("--min-size", type=int, default=12,
                    help="smallest shared subterm, in leaves, to name (default 12)")
    ap.add_argument("--max-args", type=int, default=9,
                    help="most fresh variables tried per behaviour (default 9)")
    ap.add_argument("--fuel", type=int, default=200000,
                    help="reduction steps for the whole term's normal form (default 200000)")
    a = ap.parse_args(argv)
    if a.max_args > len(VARS):
        ap.error(f"--max-args is at most {len(VARS)}")

    src = sys.stdin.read() if a.term == "-" else open(a.term, encoding="utf-8").read()
    stem = a.out or ("term" if a.term == "-" else re.sub(r"\.[^./]*$", "", a.term))
    t = hashcons(parse(src), {})

    names, order = name_shared(t, a.min_size)
    desc = {id(u): behaviour(u, a.max_args, 20000) for u in order}
    for u in order:
        if show(u) in BY_SYNTAX:
            names[id(u)], desc[id(u)] = BY_SYNTAX[show(u)]
    used = set(names.values())
    for u in order:
        std = BY_BEHAVIOUR.get(desc[id(u)])
        if std and std not in used:
            names[id(u)] = std
            used.add(std)

    distinct = len(hashcons_ids(t))
    txt = [f"size: {size(t)} leaves, {distinct} distinct applications"]
    try:
        r = normalize(t, [a.fuel])
        txt.append("normal form: " + (show(r) if size(r) <= 400 else f"<{size(r)} leaves>"))
    except (OutOfFuel, RecursionError):
        txt.append(f"normal form: not reached within {a.fuel} steps")
    txt.append("behaviour: " + (behaviour(t, a.max_args, 20000)
                                or f"none over at most {a.max_args} variables"))
    txt.append("")
    occ = tree_counts(t)
    for u in order:
        txt.append(f"{names[id(u)]} = {show(u, names, root=u)}")
        txt.append(f"    size {size(u)}, occurs {occ[id(u)]}x, behaviour: {desc[id(u)] or '?'}")
    txt.append("")
    txt.append("top = " + show(t, names, root=t))
    report = "\n".join(txt) + "\n"

    blocks = [("top", t)] + [(f"{names[id(u)]}", u) for u in order]
    with open(stem + ".txt", "w", encoding="utf-8") as f:
        f.write(report)
    with open(stem + ".svg", "w", encoding="utf-8") as f:
        f.write(svg_trees(blocks, names))
    with open(stem + ".tex", "w", encoding="utf-8") as f:
        f.write(tex_doc(blocks, names))
    wrote = [stem + ".txt", stem + ".svg", stem + ".tex"]
    if shutil.which("rsvg-convert"):
        subprocess.run(["rsvg-convert", "-f", "pdf", "-o", stem + ".pdf", stem + ".svg"], check=True)
        wrote.append(stem + ".pdf")
    if shutil.which("dot"):
        with open(stem + "-dag.dot", "w", encoding="utf-8") as f:
            f.write(dot_dag(t))
        subprocess.run(["dot", "-Tsvg", stem + "-dag.dot", "-o", stem + "-dag.svg"], check=True)
        wrote.append(stem + "-dag.svg")
    sys.stdout.write(report)
    print("wrote " + ", ".join(wrote), file=sys.stderr)


def hashcons_ids(t):
    seen, stack = set(), [t]
    while stack:
        u = stack.pop()
        if isinstance(u, tuple) and id(u) not in seen:
            seen.add(id(u))
            stack.extend(u)
    return seen


def tree_counts(t):
    occ, stack = Counter(), [t]
    while stack:
        u = stack.pop()
        occ[id(u)] += 1
        if isinstance(u, tuple):
            stack.extend(u)
    return occ


if __name__ == "__main__":
    main()
