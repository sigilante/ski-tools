#!/usr/bin/env python3
"""skispiral: typed-leaf spiral and every-atom disc figures of SKI terms.

    python3 skispiral.py TERMFILE [-o OUTSTEM] [--min-size N] [--prune X]

The renderers are those of the SKI self-interpretation paper's artifact
(sigilante/artifact-metacircular-ski, figures.py), ported to skidiag's
terms; on the same term they write the same SVG. That code is
Copyright (c) 2026 N. E. Davis, under the MIT License.

Spiral construction: start at the root heading up with length L = 10. At
each application, draw the function edge (green) at heading +25 deg with
length L, the argument edge (blue) at heading -65 deg with length 0.55 L;
continue into the function subterm with length 0.9 L and into the argument
subterm with length 0.55 L. Leaves: S filled circle, K filled square (side
1.6 r), I hollow ring (radius 0.85 r), with r = clamp(0.3 L, 0.12, 2.2);
variables are grey triangles. Function edges are 1.4x heavier than argument
edges. Subtrees whose edge length would fall below --prune are omitted, so
the spiral shows a term's global shape.

Disc: every atom drawn, angle from in-order leaf position (function
subtree first, clockwise from the top), radius from depth.

Writes OUTSTEM-spiral.svg, OUTSTEM-disc.svg, OUTSTEM-pair.svg (the two side
by side) and, when the term has shared subterms of at least --min-size
leaves (named as skidiag names them), OUTSTEM-parts.svg and
OUTSTEM-parts-disc.svg. PDFs too, if rsvg-convert is installed.
"""
import argparse
import math
import os
import re
import shutil
import subprocess
import sys
from html import escape as esc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skidiag  # noqa: E402

sys.setrecursionlimit(100000)

# ---- palette and geometry, from the paper's figure brief
RED, GREEN, BLUE, INK = "#C62828", "#3F8F2F", "#2F6FC9", "#444441"
TF, TA = math.radians(25), math.radians(65)
RF, RA = 0.9, 0.55
L0 = 10.0
PRUNE = 0.02
TEXT_WIDTH_PT = 454.0   # the paper's \linewidth; strip labels are sized for it


def is_atom(t):
    return not isinstance(t, tuple)


def layout(term, prune=PRUNE):
    """Turtle walk. Returns (segments, leaves): segments are
    (x1,y1,x2,y2,is_arg); leaves are (x,y,kind,r)."""
    segs, leaves = [], []
    stack = [(term, 0.0, 0.0, math.pi / 2, L0)]
    while stack:
        t, x, y, ang, L = stack.pop()
        if is_atom(t):
            leaves.append((x, y, t, max(0.12, min(2.2, 0.3 * L))))
            continue
        if L < prune:
            continue
        fa = ang + TF
        fx, fy = x + L * math.cos(fa), y - L * math.sin(fa)
        aa = ang - TA
        al = L * RA
        ax, ay = x + al * math.cos(aa), y - al * math.sin(aa)
        segs.append((x, y, fx, fy, False))
        segs.append((x, y, ax, ay, True))
        stack.append((t[1], ax, ay, aa, al))
        stack.append((t[0], fx, fy, fa, L * RF))
    return segs, leaves


def _bounds(segs, leaves):
    xs = [0.0]; ys = [0.0]
    for s in segs:
        xs += [s[0], s[2]]; ys += [s[1], s[3]]
    for l in leaves:
        xs += [l[0] - l[3], l[0] + l[3]]; ys += [l[1] - l[3], l[1] + l[3]]
    return min(xs), min(ys), max(xs), max(ys)


def panel_svg(term, prune=PRUNE):
    """SVG fragment for one term's spiral, in local coordinates. Returns
    (fragment, viewbox tuple, leaves drawn)."""
    segs, leaves = layout(term, prune)
    x0, y0, x1, y1 = _bounds(segs, leaves)
    w, h = max(x1 - x0, 8), max(y1 - y0, 8)
    p = 0.08 * max(w, h) + 1.5
    E = max(w, h)
    w_fn, w_arg = E / 230, E / 320
    ns = f'stroke-width="{E / 400:.3f}"'
    out = []
    for (a, b, c, d, is_arg) in segs:
        col = BLUE if is_arg else GREEN
        wd = w_arg if is_arg else w_fn
        out.append(f'<line x1="{a:.1f}" y1="{b:.1f}" x2="{c:.1f}" y2="{d:.1f}" '
                   f'stroke="{col}" stroke-width="{wd:.3f}" stroke-linecap="round"/>')
    for (x, y, k, r) in leaves:
        if k == "S":
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{RED}"/>')
        elif k == "K":
            s = 1.6 * r
            out.append(f'<rect x="{x - s/2:.2f}" y="{y - s/2:.2f}" width="{s:.2f}" height="{s:.2f}" fill="{RED}"/>')
        elif k == "I":
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{0.85*r:.2f}" fill="none" '
                       f'stroke="{RED}" stroke-width="{max(0.3*r, E/400):.3f}"/>')
        else:  # a variable
            s = 1.6 * r
            out.append(f'<polygon points="{x:.2f},{y - s/2:.2f} {x - s/2:.2f},{y + s/2:.2f} {x + s/2:.2f},{y + s/2:.2f}" fill="#7A7F87"/>')
    rr = 0.018 * max(w, h) + 0.35
    out.append(f'<circle cx="0" cy="0" r="{rr:.2f}" fill="none" stroke="{INK}" {ns}/>')
    return "\n".join(out), (x0 - p, y0 - p, w + 2 * p, h + 2 * p), len(leaves)


def _nodes(term):
    """[depth, leaf kind or None, parent, is_arg, pos] per tree node. Leaves
    get consecutive in-order positions (function subtree first); internal
    nodes get the mean of their children's."""
    nodes, children = [], {}
    work = [(term, 0, None, False)]
    while work:
        t, d, parent, is_arg = work.pop()
        idx = len(nodes)
        nodes.append([d, t if is_atom(t) else None, parent, is_arg, None])
        if parent is not None:
            children.setdefault(parent, []).append(idx)
        if not is_atom(t):
            work.append((t[1], d + 1, idx, True))
            work.append((t[0], d + 1, idx, False))    # popped first
    counter = 0
    for n in nodes:
        if n[1] is not None:
            n[4] = counter; counter += 1
    for k in range(len(nodes) - 1, -1, -1):            # children follow their parent
        if nodes[k][1] is None:
            ks = children[k]
            nodes[k][4] = sum(nodes[c][4] for c in ks) / len(ks)
    return nodes, counter


def radial_frag(term, prune=None, dr=2.2):
    """Every atom drawn, as a disc. Returns (fragment, viewbox, leaf count)
    like panel_svg. `prune` is accepted for strip() and ignored."""
    nodes, n_leaves = _nodes(term)
    maxd = max(n[0] for n in nodes)
    R = maxd * dr
    # leaf spacing on the outer ring is at least 1 unit: grow dr if needed
    if 2 * math.pi * R < n_leaves * 1.0 and maxd:
        dr = n_leaves / (2 * math.pi * maxd); R = maxd * dr

    def xy(n):
        th = -math.pi / 2 + 2 * math.pi * n[4] / n_leaves
        r = n[0] * dr
        return r * math.cos(th), r * math.sin(th)
    spacing = 2 * math.pi * R / max(n_leaves, 1)
    rl = max(0.32, min(1.2, 0.4 * spacing))
    w_fn = max(0.08, min(0.5, 0.11 * spacing)); w_arg = 0.7 * w_fn
    ns = f'stroke-width="{w_fn:.3f}"'
    out = []
    for n in nodes:
        if n[2] is None: continue
        x1, y1 = xy(nodes[n[2]]); x2, y2 = xy(n)
        col, wd = (BLUE, w_arg) if n[3] else (GREEN, w_fn)
        out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                   f'stroke="{col}" stroke-width="{wd:.3f}" stroke-linecap="round"/>')
    for n in nodes:
        if n[1] is None: continue
        x, y = xy(n); k = n[1]
        if k == "S":
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{rl:.2f}" fill="{RED}"/>')
        elif k == "K":
            sd = 1.6 * rl
            out.append(f'<rect x="{x - sd/2:.2f}" y="{y - sd/2:.2f}" width="{sd:.2f}" height="{sd:.2f}" fill="{RED}"/>')
        elif k == "I":
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{0.85*rl:.2f}" fill="none" stroke="{RED}" stroke-width="{0.3*rl:.3f}"/>')
    out.append(f'<circle cx="0" cy="0" r="{max(0.6, 0.9*rl):.2f}" fill="none" stroke="{INK}" {ns}/>')
    p = 1.5
    return "\n".join(out), (-R - p, -R - p, 2 * R + 2 * p, 2 * R + 2 * p), n_leaves


def single(frag_fn, term, title, path):
    frag, (vx, vy, vw, vh), n = frag_fn(term)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}" '
           f'width="100%" role="img" aria-label="{esc(title)}">\n'
           f'<title>{esc(title)}</title>\n{frag}\n</svg>\n')
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return n


def strip(panels, path, aria, cell=100.0, gap=8.0, render=None,
          label_pt=8.0, label_font="IBM Plex Mono, Menlo, monospace"):
    """Several panels in a row, each scaled to fill a square cell (leaf sizes
    are therefore not comparable across panels).
    panels: list of (term, label, prune[, renderer])."""
    n = len(panels)
    W = n * cell + (n + 1) * gap
    fs = label_pt * W / TEXT_WIDTH_PT
    label_h = 2.2 * fs
    H = cell + 2 * gap + label_h
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="100%" '
           f'role="img" aria-label="{esc(aria)}">', f'<title>{esc(aria)}</title>']
    counts = []
    for i, panel in enumerate(panels):
        term, label, prune = panel[:3]
        rend = panel[3] if len(panel) > 3 else (render or panel_svg)
        frag, (vx, vy, vw, vh), cnt = rend(term, prune)
        counts.append(cnt)
        cx = gap + i * (cell + gap)
        s = cell / max(vw, vh)
        ox = cx + (cell - vw * s) / 2 - vx * s
        oy = gap + (cell - vh * s) / 2 - vy * s
        out.append(f'<rect x="{cx:.1f}" y="{gap:.1f}" width="{cell:.1f}" height="{cell:.1f}" '
                   f'fill="#FFFFFF" stroke="{INK}" stroke-width="0.4"/>')
        out.append(f'<g transform="translate({ox:.3f},{oy:.3f}) scale({s:.4f})">{frag}</g>')
        out.append(f'<text x="{cx + cell/2:.1f}" y="{gap + cell + label_h - 0.5*fs:.1f}" text-anchor="middle" '
                   f'font-family="{label_font}" font-size="{fs:.2f}" fill="{INK}">{esc(label)}</text>')
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("term", help="file holding the term, or - for stdin")
    ap.add_argument("-o", "--out", help="output stem (default: the term file's stem)")
    ap.add_argument("--min-size", type=int, default=12,
                    help="smallest shared subterm, in leaves, drawn as a part (default 12)")
    ap.add_argument("--prune", type=float, default=PRUNE,
                    help=f"spiral: omit subtrees whose edge is shorter (default {PRUNE})")
    a = ap.parse_args(argv)

    src = sys.stdin.read() if a.term == "-" else open(a.term, encoding="utf-8").read()
    stem = a.out or ("term" if a.term == "-" else re.sub(r"\.[^./]*$", "", a.term))
    t = skidiag.hashcons(skidiag.parse(src), {})
    n_all = skidiag.size(t)
    spiral = lambda u: panel_svg(u, a.prune)

    lines, wrote = [], []
    n = single(spiral, t, "spiral", stem + "-spiral.svg")
    lines.append(f"spiral: {n} of {n_all} leaves drawn")
    n = single(radial_frag, t, "every atom drawn", stem + "-disc.svg")
    depth = max(nd[0] for nd in _nodes(t)[0])
    lines.append(f"disc: {n} leaves, depth {depth}")
    strip([(t, "spiral", a.prune), (t, "every atom", a.prune, radial_frag)],
          stem + "-pair.svg", "spiral beside every-atom disc", label_pt=10.0)
    wrote += [stem + s for s in ("-spiral.svg", "-disc.svg", "-pair.svg")]

    names, order = skidiag.name_shared(t, a.min_size)
    for u in order:
        if skidiag.show(u) in skidiag.BY_SYNTAX:
            names[id(u)] = skidiag.BY_SYNTAX[skidiag.show(u)][0]
    if order:
        parts = [(u, f"{names[id(u)]} · {skidiag.size(u)}", a.prune) for u in order]
        drawn = strip(parts, stem + "-parts.svg", "shared subterms, spiral")
        strip(parts, stem + "-parts-disc.svg", "shared subterms, every atom", render=radial_frag)
        wrote += [stem + "-parts.svg", stem + "-parts-disc.svg"]
        for (u, label, _), d in zip(parts, drawn):
            lines.append(f"part {label}: spiral draws {d} of {skidiag.size(u)}")

    if shutil.which("rsvg-convert"):
        for svg in list(wrote):
            subprocess.run(["rsvg-convert", "-f", "pdf", "-o", svg[:-4] + ".pdf", svg], check=True)
            wrote.append(svg[:-4] + ".pdf")
    print("\n".join(lines))
    print("wrote " + ", ".join(wrote), file=sys.stderr)


if __name__ == "__main__":
    main()
