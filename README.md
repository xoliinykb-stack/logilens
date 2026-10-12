# logilens

logilens checks [Logisim](http://www.cburch.com/logisim/) circuits from the terminal. It finds wiring mistakes, prints truth tables and Karnaugh maps, and compares a two-level circuit with the proven minimum where it can.

[![CI](https://github.com/xoliinykb-stack/logilens/actions/workflows/ci.yml/badge.svg)](https://github.com/xoliinykb-stack/logilens/actions/workflows/ci.yml) [![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

Русская версия: [README.ru.md](README.ru.md).

```sh
brew install xoliinykb-stack/tap/logilens
```

Logisim is a free educational circuit simulator by Carl Burch. logilens reads the `.circ` files of Logisim 2.7.1. This is the start of `logilens --lang en analyze --spec examples/converter.spec.txt examples/converter_nand_nor.circ`:

```text
╭─ logilens · circuit report ──────────────────────────────────────────────────────────────────────╮
│                                                                                                  │
│  File           converter_nand_nor.circ  (circuit main)                                          │
│  Engine         Logisim 2.7.1 · backend java                                                     │
│  I/O            inputs: 5 (a b c d e) → outputs: 8 (A_N B_N C_N D_N A_R B_R C_R D_R)             │
│  Components     NAND ×19, NOR ×18, Pin ×13                                                       │
│  Type           combinational                                                                    │
│  Specification  converter.spec.txt (code table, 12 rows)                                         │
│  Verdict        ✓ OPTIMAL                                                                        │
│                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
Wiring check (lint) ────────────────────────────────────────────────────────────────────────────────
✓ 0 problems — no wiring problems found
Specification check ────────────────────────────────────────────────────────────────────────────────
A_N, B_N, C_N, D_N  ✓ 12/12 rows correct
A_R, B_R, C_R, D_R  ✓ 12/12 rows correct
```

The rest of the report has the Karnaugh maps, the result of every minimization method, and the rewriting to NAND and NOR.

## Install

### Homebrew (macOS)

```sh
brew install xoliinykb-stack/tap/logilens
logilens doctor
```

`brew install` also installs OpenJDK and downloads `logisim.jar` from Logisim 2.7.1 (checked by SHA-256), so the Java engine works right away. Espresso and the Java helper are built during the install. To remove it, run `brew uninstall logilens`.

### pipx

```sh
pipx install git+https://github.com/xoliinykb-stack/logilens
logilens setup        # builds Espresso and the Java helper into the user cache
```

This needs Python 3.11 or newer, plus `make` and a C compiler for Espresso (on macOS, `xcode-select --install`). Java and `logisim.jar` are optional: without them, logilens uses its built-in Python engine. See [Java engine and Python engine](#java-engine-and-python-engine).

### Install script

From a clone of the repository:

```sh
bash scripts/install.sh                 # virtualenv in ~/.local/share/logilens, command in ~/.local/bin
bash scripts/install.sh --download-jar  # also download Logisim 2.7.1, checked by SHA-256
bash scripts/install.sh --uninstall     # remove it again
```

The script has the same requirements as pipx.

## Quick start

The repository has three example circuits in [examples/](examples/). Homebrew installs the same files, so after `brew install` run the commands below from `$(brew --prefix logilens)/share/logilens`.

```sh
logilens lint examples/converter_draft.circ
logilens check --spec examples/converter.spec.txt examples/converter_nand_nor.circ
logilens analyze --spec examples/converter.spec.txt examples/converter_draft.circ
logilens seq --input 0110 examples/moore_fsm.circ
```

`converter_draft.circ` is a first attempt at a 5-to-4-bit code converter: `lint` reports an unconnected gate input, duplicate pin labels, loose wires, and unlabeled outputs, and `analyze` shows that both halves can be built with fewer gates. `converter_nand_nor.circ` is the corrected version and passes all 12 rows of the specification. `moore_fsm.circ` is a small Moore machine for `seq`.

## Features

* Wiring checks with 14 rules, L001 to L014. Every message says how to fix the problem.
* Truth tables, Karnaugh maps for 2 to 6 variables, and minimal SOP and POS forms.
* Optimality proofs with an integer linear program (HiGHS). Quine–McCluskey, Petrick, Tison, and Espresso run alongside for comparison.
* Checks against a specification: a code table, a truth table, or formulas.
* Rewriting to NAND and NOR, with gate and input costs.
* Flip-flops, Moore and Mealy machines, state encodings, and timing diagrams.
* Reports in the terminal, and as Markdown, HTML, or JSON files.

## Commands

| Command | What it does |
|---------|--------------|
| `parse` | Lists circuits, components, and input and output pins. |
| `lint` | Checks the wiring with rules L001–L014. |
| `check` | Compares the circuit with a specification: a code table, a truth table, or formulas. |
| `analyze` | Prints the truth table, Karnaugh maps, minimal SOP and POS, NAND/NOR rewriting, and the optimality verdict. |
| `seq` | Shows flip-flops, the transition table, the Moore or Mealy type, the state graph, and a timing diagram. |
| `report` | Writes the full analysis to the terminal, or to a Markdown, HTML, or JSON file. |
| `doctor` | Shows which optional tools are available: Java, Logisim, Espresso, Graphviz. |
| `setup` | Builds the Java helper and Espresso into the user cache. |
| `cache clear` | Deletes the cached builds. |

Every command accepts `--help`. [docs/USAGE.md](docs/USAGE.md) describes all options.

## Interactive view

Run `logilens` with no command in a terminal to open a file picker. `logilens FILE --spec SPEC` opens one file directly. Press `?` inside the view for the list of keys. Outside a terminal, the command prints the list of commands.

## Java engine and Python engine

`--backend java` runs the Logisim 2.7.1 engine itself, through a small Java helper. It needs a JDK (Java 11 or newer) and `logisim.jar`, which is not part of this repository or of the Python package. `--backend python` uses a built-in simulator that needs nothing extra. The default, `auto`, takes Java when both are found. `logilens parse --crossval FILE` checks the Python engine against Logisim, see [docs/USAGE.md](docs/USAGE.md#parse).

## Limitations

* logilens reads Logisim 2.7.1 files, and that version is the reference. Files saved by Logisim-evolution 3.x are read experimentally, with the 2.7.1 rules. No other version is tested.
* A circuit is called optimal only with a proof. Above 8 inputs, the ILP chooses only among multi-output prime implicants.
* Only two-level forms are minimized. Multi-level circuits are never called minimal.
* Groups with more than 10 variables are not minimized. Truth tables are limited to 20 input bits.
* Without `--spec`, don't cares are unknown, so the circuit's own fully specified function is minimized.
* Sequential analysis uses Python models of the flip-flops. RAM and ROM are only described.

## Documentation

* [docs/USAGE.md](docs/USAGE.md): every command, its options, the specification formats, and the exit codes.
* [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): common setup problems and their fixes.

Bugs and questions go to the [issue tracker](https://github.com/xoliinykb-stack/logilens/issues), security problems as described in [SECURITY.md](SECURITY.md).

## License

logilens is free software under the GNU General Public License, version 3 or later. See [LICENSE](LICENSE). It bundles Espresso (MIT), see [third_party/espresso/LICENSE](third_party/espresso/LICENSE). logilens is not affiliated with Logisim or Carl Burch.
