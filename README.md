# ski-tools

Small tools for reading and presenting SKI combinator terms. Both read the same input syntax (see skidiag's Input).

## skidiag: application-tree diagrams

`skidiag.py` draws a term as Barendregt-style application trees. Each `@` node applies its left child to its right child. Shared subterms are named and drawn once, so a 990-leaf term becomes a top-level tree plus a legend of definitions.

```
python3 skidiag.py examples/fixpoint.ski --min-size 4
```

```
Y = S D (S B D)
    size 14, occurs 2x, behaviour: fixed point: Y f = f (Y f)
D = K (S I I)
    size 4, occurs 4x, behaviour: λab. b b
B = S (K S) K
    size 4, occurs 3x, behaviour: λabc. a (b c)

top = Y (S (K B) (S (K Y) K))
```

### Input

- **Atoms.** `S`, `K` and `I`, parentheses, and free variables (lower-case identifiers).
- **Application.** Left-associative. `⬝` is also read as application, so Lean's `S ⬝ K ⬝ I` works.
- **Errors.** Any other character is an error.
- **Standard input.** Pass `-` as the file to read the term from standard input.

### Output

For an output stem `OUT` (by default, the term file's name without its extension):

| File | Contents |
|---|---|
| `OUT.txt` | size, normal form, and each name's definition, size, count and behaviour |
| `OUT.svg` | ordered application trees, named subterms boxed |
| `OUT.pdf` | the same, if `rsvg-convert` is installed |
| `OUT.tex` | TikZ `forest` trees in a standalone LaTeX document; copy a `forest` block into a paper |
| `OUT-dag.svg` | the whole term with every shared subterm drawn once, if Graphviz is installed |

### How names are chosen

- **Which subterms.** A subterm is named when it occurs at least twice and has at least `--min-size` leaves (default 12).
- **No useless names.** A subterm is left unnamed when its only occurrence sits once inside another named subterm, since naming it adds no sharing.
- **Default names.** Names are letters in order of first appearance, skipping `S K I B C T M W Y`.
- **Behaviour.** The tool applies each named subterm to fresh variables and reduces it, leftmost-outermost with fuel. The fewest variables that leave a combinator-free result give its behaviour, for example `λabc. a (b c)`.
- **Standard names.** A subterm whose behaviour matches a standard combinator gets that name: `B`, `C`, `T`, `M`, `W`, `I`, `K`, `S` or `KI`. Curry's `Y` and `Ω` are matched by syntax.
- **`?` behaviour.** `?` means there was no combinator-free result within `--max-args` variables. Usually such a subterm expects data arguments, or it recurses.

### Options

| Option | Default | Meaning |
|---|---|---|
| `-o OUT` | term file's stem | output stem |
| `--min-size N` | 12 | smallest shared subterm to name, in leaves |
| `--max-args N` | 9 | most fresh variables tried for a behaviour |
| `--fuel N` | 200000 | reduction steps allowed for the whole term's normal form |

### Requirements

Python 3.8 or later, standard library only. `rsvg-convert` (PDF) and Graphviz `dot` (the DAG) are optional.

## skispiral: spiral and disc figures

`skispiral.py` draws a term in the typed-leaf notation of the SKI self-interpretation paper. Its renderers are ported from that paper's artifact (`sigilante/artifact-metacircular-ski`, `figures.py`). On a 990-leaf term, the five figures it writes match `figures.py`'s output line for line, apart from titles.

```
python3 skispiral.py term.ski [-o OUT] [--min-size N] [--prune X]
```

- **Spiral.** Function edges are green and turn 25° left at full length. Argument edges are blue and turn 65° right at 0.55 of the length. `S` is a filled circle, `K` a filled square, `I` a ring and a variable a grey triangle. Subtrees whose edge would be shorter than `--prune` (default 0.02) are omitted, so the spiral shows a term's overall shape. The tool reports how many leaves it drew.
- **Disc.** Every atom is drawn. A leaf's angle is its left-to-right position, and its radius is its depth.

| File | Contents |
|---|---|
| `OUT-spiral.svg` | the spiral |
| `OUT-disc.svg` | the disc |
| `OUT-pair.svg` | the two side by side, as in the paper |
| `OUT-parts.svg` | each shared subterm as a spiral, named as `skidiag` names them; written only if any qualify |
| `OUT-parts-disc.svg` | the same subterms as discs |

It also writes a PDF of each, if `rsvg-convert` is installed. Each panel in a strip is scaled to fill its cell, so leaf sizes can't be compared across panels.

## Tests

```
python3 -m unittest discover -s tests
```

## Licence

MIT; see `LICENSE`.
