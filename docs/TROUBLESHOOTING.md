# Troubleshooting

Each entry starts with the message or the behavior you see. The commands are run from the repository root or with the installed `logilens`. For the options and environment variables, see [USAGE](USAGE.md#environment-variables-and-files).

## Java is not installed

```text
$ logilens --lang en --backend java parse examples/converter_nand_nor.circ
✗ The simulation engine is not available.
  Java backend unavailable: java not found
  Run `logilens doctor` to see what is missing, or use --backend python.
  Run again with --debug for details.
```

The Java engine needs `java` and `javac`. The command above used `--backend java`, so it stopped. With the default `auto`, the command falls back to the Python engine instead.

Install a JDK and check the result with `logilens doctor`. On macOS, use `brew install openjdk`. Homebrew does not link this JDK into `PATH`, but logilens finds it in the default Homebrew locations, `/opt/homebrew` and `/usr/local`. On Debian or Ubuntu, use `sudo apt install default-jdk`. For a JDK in another place, set `JAVA_HOME` to its directory.

## The Logisim jar is not found

```text
$ logilens --lang en --backend java --logisim-jar missing/logisim.jar parse examples/converter_nand_nor.circ
✗ The simulation engine is not available.
  Java backend unavailable: Logisim jar not found (use --logisim-jar or $LOGISIM_JAR)
  Run `logilens doctor` to see what is missing, or use --backend python.
  Run again with --debug for details.
```

The Java engine needs `logisim.jar` from Logisim 2.7.1. The jar is searched in the order listed in [USAGE](USAGE.md#environment-variables-and-files). On macOS, the jar inside `Logisim.app` is found automatically.

Give the path in one of these ways: `--logisim-jar PATH`, the `LOGISIM_JAR` variable, or `logisim_jar` in `config.toml`. To download Logisim 2.7.1 into the cache, run `bash scripts/install.sh --download-jar` from a checkout. A path given with `--logisim-jar` must exist. If it does not, the search stops there, and `auto` uses the Python engine.

## The Java helper is not built

`logilens doctor` shows `Logisim helper` as `not built yet`, or as `build failed`.

The helper is compiled from `java/LogisimBridge.java` against the jar the first time it is needed. The compile needs a JDK, which is the `Java compiler` row of `doctor`. Run `logilens setup` to build it now. Use `logilens setup --force` to rebuild from scratch. Read the error that `setup` prints, because it names the failing step. A different jar gets its own build the first time it is used.

## Espresso is not built

The limitations of `analyze` and `report` say `Espresso is not built (run logilens setup); its rows are empty.`

The rows of the Espresso methods stay empty. The other methods still run, and the optimality proof does not depend on Espresso.

`logilens setup` builds Espresso from the sources in the installed package. The build needs `make` and a C compiler. On macOS, run `xcode-select --install`. On Debian or Ubuntu, run `sudo apt install build-essential`. An existing binary can be used instead of a build: set `LOGILENS_ESPRESSO` to its path.

## The Python engine is used

```text
$ logilens --lang en parse examples/converter_nand_nor.circ
converter_nand_nor.circ  Logisim 2.7.1 · backend python
├── main ★
│   ├── components: NAND ×19, NOR ×18, Pin ×13
│   ├── inputs: a b c d e
│   ├── outputs: A_N B_N C_N D_N A_R B_R C_R D_R
│   └── 42 nets, 239 wires
└── Java backend unavailable (java not found); using the Python backend
```

The last line means the Java engine was not available, so `auto` chose the Python engine. The Python engine reads the port positions and the wires itself. It is checked against Logisim with `logilens parse --crossval FILE`, which needs Java.

For the Logisim engine, install a JDK and the jar, as described in the entries above. To make a missing Java an error instead of a fallback, use `--backend java`.

## Output is in the wrong language

The language is chosen in this order: the `--lang` option, the `LOGILENS_LANG` variable, then the first of `LC_ALL`, `LC_MESSAGES`, and `LANG` that is set. Languages other than `ru` and `sk` give English. A system locale of `C` gives English.

Use `--lang en` for one command, or `export LOGILENS_LANG=en` in the shell profile for all commands.

## Logisim-evolution files are read experimentally

`logilens parse` prints `Logisim-evolution file: parsed with 2.7.1 component specs (experimental)` for a file saved by Logisim-evolution 3.x.

The file is read with the rules of Logisim 2.7.1. A component that changed in Logisim-evolution can get the wrong port positions, which changes the results of `lint` and `analyze`. Logisim 2.7.1 is the reference. Where possible, build the circuit in Logisim 2.7.1 and check it with `parse --crossval`.

## A gate input is reported as unconnected

```text
$ logilens --lang en lint examples/converter_draft.circ
logilens lint converter_draft.circ
Level     Rule   Where             Problem → fix
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ERROR     L001   NOR (480,750)     input 3 of NOR (480,750) is not connected (nothing at (420,770));
                                   Logisim silently ignores it and computes the gate from the
                                   remaining inputs
                                   → draw a wire that ends exactly at (420,770), or reduce the
                                   number of inputs
```

Rule L001 reports a gate input with no wire at its position. Logisim does not show this. It ignores the input and computes the gate from the other inputs, so the circuit can look correct in Logisim and still be wrong.

Draw a wire that ends exactly at the point the message names, or reduce the number of inputs of the gate. The message gives both the point and the gate.
