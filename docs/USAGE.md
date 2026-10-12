# Command reference

The samples are real output of the current version, run on the files in [examples/](../examples/) and `tests/fixtures/` with colors off and a width of 100 columns.

## Global options

Global options go before the command: `logilens --backend python lint FILE`.

| Option | Meaning |
|---|---|
| `--lang ru\|sk\|en` | Language of the output. Default: `LOGILENS_LANG`, then the system locale, then English. |
| `--backend auto\|java\|python` | Engine. `auto` uses Java when `java`, `javac`, and the Logisim jar are found. |
| `--logisim-jar PATH` | Path to `logisim.jar` (Logisim 2.7.1). |
| `--debug` | Show Python tracebacks when an error occurs. |
| `--no-color` | Plain output. Same as `NO_COLOR=1`. |
| `--version` | Print the version and exit. |
| `-h`, `--help` | Show help for the program or for one command. |

Three more options belong to the interactive view, which opens when `logilens` runs in a terminal without a command: `logilens [--spec FILE] [--only GATES] [FILE]`. `--no-tui` prints the list of commands instead of opening the view.

## parse

Shows the circuits in a file, with their components, pins, and nets.

```text
$ logilens --lang en parse examples/converter_nand_nor.circ
converter_nand_nor.circ  Logisim 2.7.1 · backend java
└── main ★
    ├── components: NAND ×19, NOR ×18, Pin ×13
    ├── inputs: a b c d e
    ├── outputs: A_N B_N C_N D_N A_R B_R C_R D_R
    └── 42 nets, 239 wires
```

`logilens parse [--crossval] [--json] FILE`

* `--crossval` compares the Python parser with the Logisim engine: components, port positions, nets, and truth tables. It needs Java.
* `--json` prints JSON. See [Machine-readable output](#machine-readable-output---json).

## lint

Checks the wiring. Exit code 1 when an error or a warning is found.

`logilens lint [--only GATES] [--min-severity error|warning|info] [--json] FILE`

* `--only GATES` allows only the listed gate types, for example `nand,nor`. NOT is a gate type of its own.
* `--min-severity` hides the issues below the given level. Default: `info`.

| Rule | Severity | What it finds |
|---|---|---|
| L001 | error | A gate input is not connected. Logisim ignores it without a message. |
| L002 | warning | A wire end touches nothing. |
| L003 | warning | A gate output drives nothing. |
| L004 | error | Two or more outputs drive the same net. |
| L005 | info | A wire end lies on the middle of another wire. Logisim 2.7.1 joins them. |
| L006 | warning | Two wires lie on top of each other. |
| L007 | warning | A wire passes through the body of a component. |
| L008 | warning | A loop without flip-flops (asynchronous feedback). |
| L009 | error | Two pins have the same label. |
| L010 | info | Labels are inconsistent: spaces, invalid characters, or case-only differences. |
| L011 | error | A gate type outside `--only`. |
| L012 | warning | A component that the analysis does not support. |
| L013 | error | Bit widths of connected pins do not match. |
| L014 | warning | An input or output pin has no label. |

```text
$ logilens --lang en lint tests/fixtures/gen/two_drivers.circ
logilens lint two_drivers.circ
Level   Rule   Where           Problem → fix
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ERROR   L004   NOT (200,100)   net at (200,100) has 2 drivers: NOT (200,100), NOT (200,200)
                               → only one output may drive a net; remove one connection (identical
                               values hide this in simulation)
✗ errors: 1, warnings: 0, notes: 0
```

## check

Compares the circuit with a specification. Exit code 1 when any row differs.

`logilens check --spec FILE [--map SPEC=OUT,...] [--tie|--no-tie] [--circuit NAME] [--json] FILE`

* Each output of the specification is matched to a circuit output, in this order: the same label, a label prefix before `_` (`A` matches `A_N` and `A_R`), the function of the output, and the position. Case does not matter. The matching is always printed.
* `--map` sets the matching by hand: `--map 'A=A_N,A_R;B=B_N,B_R'`. Quote the value, because `;` is special in the shell.
* `--tie` and `--no-tie` merge input pins that have the same label. The default is automatic.

```text
$ logilens --lang en check --spec examples/converter.spec.txt examples/converter_nand_nor.circ
logilens check converter_nand_nor.circ  ↔  converter.spec.txt
A_N, B_N, C_N, D_N  ✓ 12/12 rows correct
A_R, B_R, C_R, D_R  ✓ 12/12 rows correct
Mapping: A → A_N, A_R (label prefix)  B → B_N, B_R (label prefix)  C → C_N, C_R (label prefix)  D →
D_N, D_R (label prefix)
ⓘ 28 don't-care rows where circuit outputs of the same spec output differ (not an error)
✓ The circuit matches the specification.
```

## analyze

Analyzes the function of each group of outputs. It prints the Karnaugh maps, the result of every minimization method, the optimality verdict, and the rewriting to NAND or NOR.

`logilens analyze [--spec FILE] [--map SPEC=OUT,...] [--outputs NAMES] [--methods NAMES] [--form auto|sop|pos|both] [--no-kmap] [--table] [--only GATES] [--tie|--no-tie] [--circuit NAME] [--json] FILE`

| Option | Meaning |
|---|---|
| `--spec FILE` | Specification. Its don't-care rows are used. Without it, the circuit's own function is minimized. |
| `--outputs NAMES` | Analyze only the groups that contain these outputs. Comma-separated. An unknown name is an error. |
| `--methods NAMES` | Minimization methods to run, comma-separated. `ilp` always runs. |
| `--form auto\|sop\|pos\|both` | `sop` is the minimal sum of products (SOP). `pos` is the minimal product of sums (POS). `auto` uses SOP for NAND and AND-OR groups, POS for NOR and OR-AND groups, and both when the technology is unclear. |
| `--no-kmap`, `--table` | Hide the Karnaugh maps, or print the full truth table. |
| `--map`, `--only`, `--tie`, `--no-tie` | As in `check` and `lint`. |
| `--circuit NAME` | Analyze this circuit instead of `main`. |
| `--json` | Print JSON (schema `logilens/report@1`). |

| Method | What it does |
|---|---|
| `qm+petrick` | Quine–McCluskey prime implicants, then Petrick's method for each output. |
| `tison+petrick` | Tison's prime sets, then Petrick's method. |
| `petrick+sharing` | Petrick's method, then shared terms between outputs. |
| `exact_mo` | Exhaustive search for the fewest distinct terms over all outputs. |
| `ilp` | Integer linear program (HiGHS). Always runs. It produces the proof. |
| `espresso:default`, `espresso:exact`, `espresso:signature`, `espresso:qm`, `espresso:so`, `espresso:efast` | Espresso in the given mode. A heuristic, so it proves nothing. |

Costs are written as gates/inputs. `as drawn` counts the circuit as it is. `as NAND/NOR` counts every NOT as a NAND or NOR with tied inputs, which is two inputs. `optimum` is the proven minimum.

| Verdict | Meaning |
|---|---|
| `OPTIMAL` | The cost of the circuit equals the proven minimum. |
| `CAN BE IMPROVED` | A cheaper form is proven. The optimal cover is printed. |
| `BEYOND TWO-LEVEL` | The structure is not two-level, so no optimality is claimed. |
| `OPTIMALITY NOT PROVEN` | The minimum could not be proven. |
| `NOT ANALYZED` | No optimality analysis was run for the group. |

```text
$ logilens --lang en analyze --spec examples/converter.spec.txt --outputs A_N --no-kmap --methods qm+petrick,espresso:default examples/converter_nand_nor.circ
Optimality summary ─────────────────────────────────────────────────────────────────────────────────
╭───┬────────────────────┬────────────┬──────────┬─────────────┬─────────┬───┬───────────╮
│ # │ Outputs            │ Technology │ as drawn │ as NAND/NOR │ optimum │ Δ │ Verdict   │
├───┼────────────────────┼────────────┼──────────┼─────────────┼─────────┼───┼───────────┤
│ 1 │ A_N, B_N, C_N, D_N │ NAND-NAND  │    19/48 │       19/48 │   19/48 │ — │ ✓ OPTIMAL │
╰───┴────────────────────┴────────────┴──────────┴─────────────┴─────────┴───┴───────────╯
```

## seq

Analyzes a sequential circuit: flip-flops, the transition table, the Moore or Mealy type, reachable states, state minimization, the cost of the next-state logic for several encodings, a timing diagram, and the state graph.

`logilens seq [--input BITS] [--dot PATH] [--circuit NAME] [--json] FILE`

* `--input BITS` adds a timing diagram for an input sequence, for example `0110`.
* `--dot PATH` writes the state graph as a Graphviz file. Draw it with `dot -Tsvg fsm.dot -o fsm.svg`. Graphviz is installed with `brew install graphviz`.

```text
$ logilens --lang en seq --input 0110 examples/moore_fsm.circ
╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Machine             Moore machine                                                                │
│ Flip-flop           D ×2 · state variables: z1, z2                                               │
│ Inputs → outputs    x → z1, z2, y                                                                │
│ Clock               clk                                                                          │
│ Initial state       00                                                                           │
│ Reachable states    4 · unreachable: —                                                           │
│ State minimization  minimal (4 states)                                                           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## report

Writes the complete analysis: the sections of `analyze`, the lint and specification results, and the sequential part for sequential circuits.

`logilens report [-f rich|md|html|json] [-o PATH] [--spec FILE] [--map SPEC=OUT,...] [--only GATES] [--tie|--no-tie] [--no-image] [--circuit NAME] FILE`

| Option | Meaning |
|---|---|
| `-f`, `--format` | `rich` (terminal, the default), `md` (Markdown), `html`, or `json`. |
| `-o`, `--output PATH` | Write the report to this file instead of the terminal. |
| `--no-image` | HTML only. Do not embed the drawing of the circuit, which needs Java. |

```text
$ logilens --lang en report -f md -o report.md --spec examples/converter.spec.txt examples/converter_nand_nor.circ
✓ written: report.md
$ head -n 8 report.md
# logilens · circuit report

|  |  |
|---|---|
| File | `converter_nand_nor.circ` (circuit `main`) |
| Engine | Logisim 2.7.1 · backend java |
| I/O | inputs: 5 (a b c d e) → outputs: 8 (A_N B_N C_N D_N A_R B_R C_R D_R) |
| Components | NAND ×19, NOR ×18, Pin ×13 |
```

## doctor

Checks the environment: Python, Java, the Logisim jar, the Java helper, Espresso, Graphviz, and the cache directory. Python is the only required tool.

`logilens doctor [--fix] [--json]`

* `--fix` builds the Java helper and Espresso when possible.
* Exit code 4 when a check fails. A `!` marks a limited feature, for example the Python engine used without the jar. A `·` marks an optional tool that is not installed.

```text
$ logilens --lang en doctor
logilens doctor
╭───┬─────────────────────┬───────────────────────────────────┬────────────────────────────────────╮
│   │ Component           │ Status                            │ How to fix                         │
├───┼─────────────────────┼───────────────────────────────────┼────────────────────────────────────┤
│ ✓ │ Python              │ 3.14.7                            │                                    │
│   │                     │ (~/.local/share/logilens/venv/bin │                                    │
│   │                     │ /python)                          │                                    │
│ ✓ │ Java runtime        │ 27                                │                                    │
│   │                     │ (/opt/homebrew/opt/openjdk/bin/ja │                                    │
│   │                     │ va)                               │                                    │
│ ✓ │ Java compiler       │ 27                                │                                    │
│   │                     │ (/opt/homebrew/opt/openjdk/bin/ja │                                    │
│   │                     │ vac)                              │                                    │
│ ✓ │ Logisim jar         │ /Applications/Logisim.app/Content │                                    │
│   │                     │ s/Resources/Java/logisim.jar      │                                    │
│   │                     │ (Logisim 2.7.1)                   │                                    │
│ ✓ │ Logisim helper      │ ~/Library/Caches/logilens/helper/ │                                    │
│   │                     │ 9b332c984233e233                  │                                    │
│ ✓ │ Espresso            │ ~/Library/Caches/logilens/espress │                                    │
│   │                     │ o/bin/espresso                    │                                    │
│ · │ Graphviz (optional) │ not installed                     │ Optional: install Graphviz         │
│   │                     │                                   │ (brew/apt install graphviz) to     │
│   │                     │                                   │ draw the state graph written by    │
│   │                     │                                   │ `seq --dot`.                       │
│ ✓ │ Cache directory     │ ~/Library/Caches/logilens         │                                    │
╰───┴─────────────────────┴───────────────────────────────────┴────────────────────────────────────╯
✓ Environment OK. Items marked ! or · only limit optional features.
```

## setup and cache clear

`logilens setup [--force]` builds the Java helper, when Java and the jar are present, and Espresso. The builds go to the user cache. The command is safe to run again. `--force` rebuilds them. Exit code 4 when Espresso cannot be built. The build needs `make` and a C compiler.

`logilens cache clear [--dry-run] [--all]` deletes the cached builds. They are rebuilt when they are needed. `--dry-run` lists what would be deleted. `--all` also deletes a `logisim.jar` in the cache directory.

```text
$ logilens --lang en setup
✓ Logisim helper  ~/Library/Caches/logilens/helper/9b332c984233e233
✓ Espresso  ~/Library/Caches/logilens/espresso/bin/espresso
$ logilens --lang en cache clear --dry-run
Would remove 2 cache entries from ~/Library/Caches/logilens
  ~/Library/Caches/logilens/espresso
  ~/Library/Caches/logilens/helper
```

## Specification formats

`--spec` reads one of three formats, detected from the content. Lines that start with `#` are comments. A comment of the form `# inputs: … outputs: …` names the signals.

Code table: one line per input code. Codes that are not listed are don't cares.

```text
# inputs: a b c d e   outputs: A B C D
0  00000 0000
1  00001 0001
```

Truth table: a header row with the names, then one row per input combination. Inputs and outputs are told apart by a `|` column, or by case: lower-case names are inputs and upper-case names are outputs. Output values are `0`, `1`, `X`, or `-` for a don't care.

```text
p q r Y
0 0 0 0
0 0 1 1
```

Formulas: one line per output. `'`, `!`, or `~` is NOT. Juxtaposition, `*`, or `&` is AND. `+` or `|` is OR. `^` is XOR. Without a `# inputs:` comment, the inputs are the variables that appear, in alphabetical order.

```text
# inputs: P Q R   outputs: y
y = P'Q + PR' + Q'R
```

## Machine-readable output (`--json`)

`parse`, `lint`, `analyze`, `check`, `seq`, and `doctor` accept `--json`. `report -f json` writes the complete report. Every document starts with a `schema` field.

| Command | Schema |
|---|---|
| `parse`, `lint`, `check`, `seq`, `doctor` | `logilens/<command>@1`, for example `logilens/lint@1` |
| `analyze --json`, `report -f json` | `logilens/report@1` |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Everything is in order. |
| 1 | Problems were found: lint errors or warnings, a specification mismatch, or a group that can be improved. |
| 2 | Wrong arguments, for example a file that does not exist or an unknown circuit or output name. |
| 3 | The file or the specification cannot be parsed, the circuit uses an unsupported component, or an internal error occurred. |
| 4 | An environment problem: Java, the jar, or Espresso is missing, or `doctor` found a failed check. |

## Environment variables and files

| Name | Purpose |
|---|---|
| `LOGILENS_LANG` | Default language: `ru`, `sk`, or `en`. `--lang` takes precedence. Without it, the first set of `LC_ALL`, `LC_MESSAGES`, and `LANG` is used. Other languages give English. |
| `NO_COLOR` | Any non-empty value turns colors off, as `--no-color` does. |
| `LOGISIM_JAR` | Path to `logisim.jar`. |
| `JAVA_HOME` | JDK whose `java` and `javac` are used. Without it, `java` and `javac` are taken from `PATH`, then from Homebrew's `openjdk`, which is not linked into `PATH`. |
| `LOGILENS_ESPRESSO` | Path to a ready Espresso binary. |
| `LOGILENS_ESPRESSO_SRC` | Espresso sources for `setup`. Not needed from a checkout or from a wheel, which carry them. |
| `LOGILENS_HOME` | Directory with a `logisim.jar`. The Homebrew package sets it. |
| `LOGILENS_HELPER_DIR` | Prebuilt Java helper. The Homebrew package sets it; the helper is used only with the jar it was built for. |
| `LOGILENS_RECENT` | File with the list of recently opened circuits in the interactive view. Default: `recent.json` in the configuration directory. |

`config.toml` in the user configuration directory can set the jar with `logisim_jar = "/path/to/logisim.jar"`. The directory is `~/Library/Application Support/logilens` on macOS and `~/.config/logilens` on Linux.

The jar is searched in this order. The first existing file is used. A path given with `--logisim-jar` that does not exist ends the search.

1. `--logisim-jar`
2. `LOGISIM_JAR`
3. `logisim_jar` in `config.toml`
4. `logisim.jar` in `LOGILENS_HOME`
5. The `Logisim.app` bundle in the Applications folder, on macOS
6. `logisim.jar` in the cache directory, where `scripts/install.sh --download-jar` puts it

The cache directory holds the compiled Java helper and the Espresso build. It is `~/Library/Caches/logilens` on macOS and `~/.cache/logilens` on Linux.
