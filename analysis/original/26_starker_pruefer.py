#!/usr/bin/env python3
"""Zusatzanalyse "starker Pruefer" (explorativ).

    .venv_analyse/bin/python analysis/26_starker_pruefer.py [--md analysis/ergebnisse_starker_pruefer_20261012.md]

Arm D erneut mit Claude Sonnet 5.5 als LLM-Pruefer (OpenRouter, Anbieter Anthropic fest) fuer die lokalen
Agenten Qwen3.8-27B und Gemma-4-31B. Verglichen wird mit
  - E aus Wiederholung 1 (gleiche Deterministik, ohne LLM-Pruefer),
  - D mit Gemma-4-31B als Pruefer, Wiederholung 1 und Mittel ueber die drei Wiederholungen.
Bewertung wie in 23_datensatz_alle_modelle.py (versiegeltes Gold, Bewerter), Intervalle wie in
20_hauptauswertung.py (Szenario als Einheit, Module gleich gewichtet, geschichtetes t-Intervall).
Gepoolt = Mittel der beiden Agenten je Szenario.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

STUDY = Path(__file__).resolve().parents[1]
LAEUFE = {"qwen38": "sp-qwen38-20261011-124547", "gemma4": "sp-gemma4-20261011-124549"}


def modul(name: str, datei: str):
    spec = importlib.util.spec_from_file_location(name, STUDY / "analysis" / datei)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


h = modul("haupt", "20_hauptauswertung.py")
ds = modul("datensatz", "23_datensatz_alle_modelle.py")


def daten() -> pd.DataFrame:
    reg = json.loads((STUDY / "analysis" / "laufregister.json").read_text())
    preistab = ds.preise()
    alt = pd.read_csv(STUDY / "analysis" / "daten" / "episoden_alle_modelle.csv")
    alt = alt[alt.modell.isin(LAEUFE)].copy()
    alt["arm2"] = alt["arm"].map({"C": "C", "E": "E", "D": "D_gemma"})
    neu = []
    for m, lauf in LAEUFE.items():
        z = pd.DataFrame(ds.zeilen_fuer(m, reg["modelle"][m], "1", [lauf], preistab))
        z["arm2"] = "D_sonnet"; neu.append(z)
    return pd.concat([alt, *neu], ignore_index=True)


def je_szenario(d: pd.DataFrame, groesse: str, bedingung: str | None) -> pd.DataFrame:
    if bedingung:
        d = d[d.bedingung == bedingung]
    return d.groupby(["modell", "modul", "szenario", "arm2"])[groesse].mean().reset_index()


def intervall(s: pd.DataFrame, a1: str, a2: str | None) -> dict:
    """a2=None: Anteil von a1; sonst Differenz a1 - a2, je Szenario gepaart."""
    werte = defaultdict(list)
    p = s.pivot_table(index=["modul", "szenario"], columns="arm2", values="wert")
    for (mod, _), r in p.iterrows():
        if pd.isna(r.get(a1)) or (a2 and pd.isna(r.get(a2))):
            continue
        werte[mod].append(r[a1] - (r[a2] if a2 else 0.0))
    return h.t_intervall(werte)


def fmt(t: dict, vorzeichen=True) -> str:
    f = "{:+.1f}" if vorzeichen else "{:.1f}"
    return f"{f.format(100 * t['schaetzung'])} ({f.format(100 * t['unten'])}, {f.format(100 * t['oben'])})"


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--md"); args = ap.parse_args()
    d = daten()
    w1 = d[(d.wiederholung == 1)]
    # Gemma-Pruefer gemittelt ueber alle Wiederholungen (D), als eigener Arm
    dmit = d[(d.arm2 == "D_gemma")].copy(); dmit["arm2"] = "D_gemma_mittel"
    basis = pd.concat([w1, dmit], ignore_index=True)
    out = ["# Zusatzanalyse starker Pruefer (explorativ)", "",
           "Arm D mit Claude Sonnet 5.5 (OpenRouter, Anthropic, Aufwand high) statt Gemma-4-31B als LLM-Pruefer; "
           "Agenten Qwen3.8-27B und Gemma-4-31B. Prozentpunkte, 95 % KI (geschichtetes t-Intervall, Szenario als "
           "Einheit). D_gemma = Wiederholung 1; D_gemma_mittel = Mittel ueber drei Wiederholungen.", ""]
    for groesse, titel in (("hoch", "Hoher Fehler"), ("erfolg", "Aufgabenerfolg")):
        for bed in (None, "faktenmanipulation"):
            out += [f"## {titel}" + (" (Fallen-Varianten)" if bed else " (alle Varianten)"), "",
                    "| Agent | E | D Gemma (W1) | D Sonnet | D Sonnet − E | D Sonnet − D Gemma (W1) | "
                    "D Sonnet − D Gemma (Mittel W1–3) |", "|---|---|---|---|---|---|---|"]
            s = je_szenario(basis, groesse, bed).rename(columns={groesse: "wert"})
            gruppen = [(m, s[s.modell == m]) for m in LAEUFE] + [
                ("gepoolt", s.groupby(["modul", "szenario", "arm2"])["wert"].mean().reset_index())]
            for name, g in gruppen:
                out.append(f"| {name} | {fmt(intervall(g, 'E', None), False)} | "
                           f"{fmt(intervall(g, 'D_gemma', None), False)} | {fmt(intervall(g, 'D_sonnet', None), False)} | "
                           f"{fmt(intervall(g, 'D_sonnet', 'E'))} | {fmt(intervall(g, 'D_sonnet', 'D_gemma'))} | "
                           f"{fmt(intervall(g, 'D_sonnet', 'D_gemma_mittel'))} |")
            out.append("")
    # Blockaden
    out += ["## Blockaden (Summen, Wiederholung 1 bzw. Sonnet-Lauf)", "",
            "| Agent | Arm | Episoden | Blockaden | berechtigt | unnoetig | Praezision % |", "|---|---|---|---|---|---|---|"]
    for m in LAEUFE:
        for arm in ("E", "D_gemma", "D_sonnet"):
            g = w1[(w1.modell == m) & (w1.arm2 == arm)]
            b, u = int(g.blockaden_berechtigt.sum()), int(g.blockaden_unnoetig.sum())
            out.append(f"| {m} | {arm} | {len(g)} | {b + u} | {b} | {u} | "
                       f"{100 * b / (b + u):.0f} |" if b + u else f"| {m} | {arm} | {len(g)} | 0 | 0 | 0 | – |")
    # Rohanteile und Kosten
    out += ["", "## Rohanteile hoher Fehler je Agent und Arm (Episoden, Wiederholung 1)", ""]
    roh = w1.groupby(["modell", "arm2"]).agg(n=("hoch", "size"), hoch=("hoch", "sum"), erfolg=("erfolg", "sum"))
    out.append("```\n" + roh.to_string() + "\n```")
    kosten = []
    for m, lauf in LAEUFE.items():
        k = json.loads((STUDY / "runs" / lauf / "pruefer_protokoll.json").read_text())
        kosten.append(f"{m}: {k['aufrufe']} Prueferaufrufe, {k['ausfaelle']} Ausfaelle, "
                      f"{k.get('kosten_openrouter_usd', 0):.2f} USD (OpenRouter), Anbieter {k.get('anbieter_gemeldet')}")
    out += ["", "## Pruefer", "", *[f"- {x}" for x in kosten]]
    text = "\n".join(out)
    print(text)
    if args.md:
        Path(args.md).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
