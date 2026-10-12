"""Glossary of logic-design terms in the three interface languages (used by renderers and the TUI help)."""

from __future__ import annotations

from dataclasses import dataclass

from logilens.i18n import normalize_lang


@dataclass(frozen=True)
class Term:
    """One term: short name per language and a one-line explanation per language."""

    ru: str
    sk: str
    en: str
    ru_def: str
    sk_def: str
    en_def: str

    def name(self, lang: str) -> str:
        return getattr(self, normalize_lang(lang))

    def definition(self, lang: str) -> str:
        return getattr(self, normalize_lang(lang) + "_def")


GLOSSARY: dict[str, Term] = {
    "mdnf": Term("МДНФ", "MDNF", "minimal SOP",
                 "минимальная дизъюнктивная нормальная форма — сумма произведений, реализуется на NAND-NAND",
                 "minimálna disjunktívna normálna forma — súčet súčinov, realizácia NAND-NAND",
                 "minimal disjunctive normal form — sum of products, built as NAND-NAND"),
    "mknf": Term("МКНФ", "MKNF", "minimal POS",
                 "минимальная конъюнктивная нормальная форма — произведение сумм, реализуется на NOR-NOR",
                 "minimálna konjunktívna normálna forma — súčin súčtov, realizácia NOR-NOR",
                 "minimal conjunctive normal form — product of sums, built as NOR-NOR"),
    "kmap": Term("карта Карно", "Karnaughova mapa", "Karnaugh map",
                 "таблица значений функции в коде Грея; соседние клетки отличаются одной переменной",
                 "tabuľka hodnôt funkcie v Grayovom kóde; susedné políčka sa líšia v jednej premennej",
                 "function table in Gray-code order; adjacent cells differ in one variable"),
    "dont_care": Term("неопределённое значение", "neurčený stav", "don't care",
                      "значение выхода не задано (X); его можно доопределить при минимизации",
                      "hodnota výstupu nie je zadaná (X); pri minimalizácii ju možno ľubovoľne zvoliť",
                      "unspecified output value (X); the minimizer may choose it freely"),
    "term": Term("член", "člen", "term",
                 "одно произведение (МДНФ) или одна сумма (МКНФ); на схеме — один гейт первого уровня",
                 "jeden súčin (MDNF) alebo jeden súčet (MKNF); v obvode jedno hradlo prvej úrovne",
                 "one product (SOP) or one sum (POS); one first-level gate in the circuit"),
    "prime_implicant": Term("простой импликант", "prostý implikant", "prime implicant",
                            "импликант, который нельзя расширить", "implikant, ktorý sa nedá zväčšiť",
                            "an implicant that cannot be enlarged"),
    "group_minimization": Term("групповая минимизация", "skupinová minimalizácia", "multi-output minimization",
                               "минимизация нескольких выходов с общими членами",
                               "minimalizácia viacerých výstupov so spoločnými členmi",
                               "minimizing several outputs that share terms"),
    "transition_table": Term("таблица переходов", "prechodová tabuľka", "transition table",
                             "текущее состояние × вход → следующее состояние, выход",
                             "aktuálny stav × vstup → nasledujúci stav, výstup",
                             "current state × input → next state, output"),
    "flip_flop": Term("триггер", "preklápací obvod", "flip-flop",
                      "элемент памяти на один бит (D, T, JK, SR)", "jednobitový pamäťový prvok (D, T, JK, SR)",
                      "one-bit memory element (D, T, JK, SR)"),
    "excitation_table": Term("таблица возбуждения", "budiaca tabuľka", "excitation table",
                             "какие входы триггера дают нужный переход", "aké vstupy preklápacieho obvodu dajú prechod",
                             "which flip-flop inputs produce a required transition"),
    "moore": Term("автомат Мура", "Moorov automat", "Moore machine",
                  "выход зависит только от состояния", "výstup závisí len od stavu", "output depends on the state only"),
    "mealy": Term("автомат Мили", "Mealyho automat", "Mealy machine",
                  "выход зависит от состояния и входа", "výstup závisí od stavu a vstupu",
                  "output depends on state and input"),
    "nand": Term("NAND (↑, штрих Шеффера)", "NAND (↑, Shefferova funkcia)", "NAND (↑, Sheffer stroke)",
                 "НЕ-И", "NAND", "NOT-AND"),
    "nor": Term("NOR (↓, стрелка Пирса)", "NOR (↓, Peirceova funkcia)", "NOR (↓, Peirce arrow)",
                "НЕ-ИЛИ", "NOR", "NOT-OR"),
    "negator": Term("инвертор (NOT)", "negátor (NOT)", "inverter (NOT)",
                    "считается как NAND/NOR со связанными входами: 1 член, 2 входа",
                    "počíta sa ako NAND/NOR so spojenými vstupmi: 1 člen, 2 vstupy",
                    "counted as a NAND/NOR with tied inputs: 1 gate, 2 inputs"),
}


def form_term(form_value: str) -> str:
    """Glossary id of a two-level form value ('SOP' -> 'mdnf')."""
    return "mdnf" if form_value.upper() == "SOP" else "mknf"


def term(term_id: str, lang: str) -> str:
    """Localized name of a glossary term (the id itself when unknown)."""
    entry = GLOSSARY.get(term_id)
    return entry.name(lang) if entry else term_id


__all__ = ["GLOSSARY", "Term", "form_term", "term"]
