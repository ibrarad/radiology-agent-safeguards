#!/usr/bin/env python3
"""Modellvergleich ueber alle Agentenmodelle (nachtraeglich). Die eingefrorene Einzelauswertung je Modell bleibt analysis/20_hauptauswertung.py.

    .venv_analyse/bin/python analysis/24_modellvergleich.py [--md bericht.md]

Eingang: analysis/daten/episoden_alle_modelle.csv (analysis/23_datensatz_alle_modelle.py).
Nur Wiederholung 1 und nur vollstaendige Modelle (273 Episoden) gehen in den Vergleich ein.

B  Gepooltes Modell: GEE, logistisch, Cluster = Grundszenario, austauschbare Korrelation.
   (1) hoch ~ Arm * Bedingung + Modell      -> gepoolte Odds Ratios E vs C, D vs E
   (2) hoch ~ Arm * Modell + Bedingung      -> Heterogenitaet: Wald-Test Arm x Modell
   dasselbe fuer Aufgabenerfolg.
C  Sicherheit gegen Nutzen: Anteile hoch und Erfolg je Modell x Arm (Rohanteile).
D  Fallen: Anteil der Fallen-Episoden mit hohem Fehler, davon Falle vorher gelesen.
E  Schutzschichten: berechtigte und unnoetige Blockaden, Praezision = berechtigt / alle.
G  Szenario-Schwierigkeit: Zahl der Modelle mit hohem Fehler je Grundszenario in Arm C.
H  Aufwand: USD, Ausgabetoken, Modellzeit und Werkzeugaufrufe je Episode.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

STUDY_ROOT = Path(__file__).resolve().parents[1]
DATEN = STUDY_ROOT / "analysis" / "daten" / "episoden_alle_modelle.csv"


def tab(df: pd.DataFrame, fmt: str = "{:.1f}") -> str:
    kopf = "| " + " | ".join(str(c) for c in df.columns) + " |"
    trenn = "|" + "|".join("---:" if pd.api.types.is_numeric_dtype(df[c]) else "---" for c in df.columns) + "|"
    zeilen = []
    for _, r in df.iterrows():
        zeilen.append("| " + " | ".join(fmt.format(v) if isinstance(v, (float, np.floating)) else str(v)
                                       for v in r) + " |")
    return "\n".join([kopf, trenn, *zeilen])


def gee(formel: str, d: pd.DataFrame):
    m = smf.gee(formel, groups="szenario", data=d, family=sm.families.Binomial(),
                cov_struct=sm.cov_struct.Exchangeable())
    return m.fit()


def or_zeile(res, name: str, kontrast: np.ndarray) -> dict:
    est = float(kontrast @ res.params.values)
    se = float(np.sqrt(kontrast @ res.cov_params().values @ kontrast))
    return {"Kontrast": name, "OR": np.exp(est), "95 % KI unten": np.exp(est - 1.96 * se),
            "95 % KI oben": np.exp(est + 1.96 * se),
            "p": float(2 * (1 - __import__("scipy").stats.norm.cdf(abs(est / se))))}


def kontrast(res, plus: list[str], minus: list[str]) -> np.ndarray:
    k = np.zeros(len(res.params))
    namen = list(res.params.index)
    for n in plus:
        k[namen.index(n)] += 1
    for n in minus:
        k[namen.index(n)] -= 1
    return k


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--md"); args = ap.parse_args()
    d = pd.read_csv(DATEN)
    d = d[d["wiederholung"] == 1]
    n = d.groupby("modell").size()
    voll = n[n == 273].index.tolist()
    teil = n[n != 273]
    d = d[d["modell"].isin(voll)].copy()
    reihenfolge = d.drop_duplicates("modell").set_index("modell")["label"]
    d["arm"] = pd.Categorical(d["arm"], ["C", "E", "D"])
    d["bedingung"] = pd.Categorical(d["bedingung"], ["sauber", "faktenmanipulation"])
    out = ["# Modellvergleich (nachtraeglich, explorativ)", "",
           f"Vollstaendige Modelle (Wiederholung 1, je 273 Episoden): {', '.join(reihenfolge)}."]
    if len(teil):
        out.append("Noch unvollstaendig und ausgeschlossen: " +
                   ", ".join(f"{m} ({k} Episoden)" for m, k in teil.items()) + ".")

    # C/E/H: Kennzahlen je Modell x Arm
    g = d.groupby(["label", "arm"], observed=True)
    kz = pd.DataFrame({
        "hoch %": g["hoch"].mean() * 100,
        "hoch sauber %": d[d.bedingung == "sauber"].groupby(["label", "arm"], observed=True)["hoch"].mean() * 100,
        "hoch Falle %": d[d.bedingung == "faktenmanipulation"].groupby(["label", "arm"], observed=True)["hoch"].mean() * 100,
        "Erfolg %": g["erfolg"].mean() * 100,
        "Blockaden berechtigt": g["blockaden_berechtigt"].sum(),
        "Blockaden unnoetig": g["blockaden_unnoetig"].sum(),
    }).reset_index()
    kz["Praezision Blockaden %"] = np.where(
        kz["Blockaden berechtigt"] + kz["Blockaden unnoetig"] > 0,
        100 * kz["Blockaden berechtigt"] / (kz["Blockaden berechtigt"] + kz["Blockaden unnoetig"]), np.nan)
    for c in ("Blockaden berechtigt", "Blockaden unnoetig"):
        kz[c] = kz[c].astype(int)
    out += ["", "## C/E: Sicherheit, Nutzen, Blockaden je Modell und Arm (Rohanteile)", "", tab(kz)]

    # D: Fallen
    fm = d[d.bedingung == "faktenmanipulation"]
    fz = fm.groupby("label").apply(lambda x: pd.Series({
        "Fallen-Episoden": len(x), "mit hohem Fehler": int(x["hoch"].sum()),
        "davon Falle vorher gelesen": int(x.loc[x["hoch"] == 1, "falle_gelesen"].fillna(0).astype(float).sum()),
    }), include_groups=False).reset_index()
    fz["hoch %"] = 100 * fz["mit hohem Fehler"] / fz["Fallen-Episoden"]
    out += ["", "## D: Fallen (alle Arme)", "", tab(fz)]

    # H: Aufwand
    h = d.groupby("label").agg(**{"USD je Episode": ("usd", "mean"), "Ausgabetoken je Episode": ("tokens_aus", "mean"),
                                  "Modellzeit s je Episode": ("dauer_modell_s", "mean"),
                                  "Werkzeugaufrufe je Episode": ("werkzeugaufrufe", "mean"),
                                  "USD gesamt": ("usd", "sum")}).reset_index()
    out += ["", "## H: Aufwand je Episode (Mittel ueber Arme)", "", tab(h, "{:.3f}")]

    # G: Szenario-Schwierigkeit (Arm C)
    c = d[d.arm == "C"].groupby(["szenario", "label"])["hoch"].max().unstack()
    sz = c.sum(axis=1).value_counts().sort_index()
    out += ["", "## G: Szenarien nach Zahl der Modelle mit hohem Fehler (Arm C, sauber oder Falle)", "",
            tab(pd.DataFrame({"Modelle mit Fehler": sz.index, "Szenarien": sz.values}))]
    schwer = c[c.sum(axis=1) >= max(2, len(voll) - 1)]
    if len(schwer):
        out += ["", f"Szenarien mit Fehler bei mindestens {max(2, len(voll) - 1)} Modellen: "
                + ", ".join(schwer.index)]

    # B: gepooltes GEE
    for ziel in ("hoch", "erfolg"):
        r1 = gee(f"{ziel} ~ C(arm) * C(bedingung) + C(modell)", d)
        p = list(r1.params.index)
        ec = kontrast(r1, ["C(arm)[T.E]"], [])
        de = kontrast(r1, ["C(arm)[T.D]"], ["C(arm)[T.E]"])
        # gemittelt ueber beide Bedingungen (Interaktion halb gewichtet)
        iE = "C(arm)[T.E]:C(bedingung)[T.faktenmanipulation]"
        iD = "C(arm)[T.D]:C(bedingung)[T.faktenmanipulation]"
        ec_m = ec + 0.5 * kontrast(r1, [iE], [])
        de_m = de + 0.5 * kontrast(r1, [iD], [iE])
        zeilen = [or_zeile(r1, "E vs C, sauber", ec), or_zeile(r1, "D vs E, sauber", de),
                  or_zeile(r1, "E vs C, Falle", ec + kontrast(r1, [iE], [])),
                  or_zeile(r1, "D vs E, Falle", de + kontrast(r1, [iD], [iE])),
                  or_zeile(r1, "E vs C, gemittelt", ec_m), or_zeile(r1, "D vs E, gemittelt", de_m)]
        r2 = gee(f"{ziel} ~ C(arm) * C(modell) + C(bedingung)", d)
        inter = [i for i, nm in enumerate(r2.params.index) if nm.startswith("C(arm)") and ":C(modell)" in nm]
        L = np.zeros((len(inter), len(r2.params))); L[range(len(inter)), inter] = 1
        w = r2.wald_test(L, scalar=True)
        out += ["", f"## B: Gepooltes Modell, Zielgroesse '{ziel}' (GEE, Cluster Szenario)", "",
                tab(pd.DataFrame(zeilen), "{:.3f}"), "",
                f"Heterogenitaet Arm x Modell (Wald, {len(inter)} df): Chi2 = {float(w.statistic):.2f}, "
                f"p = {float(w.pvalue):.4f}"]
    text = "\n".join(out) + "\n"
    print(text)
    if args.md:
        with open(args.md, "x", encoding="utf-8") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
