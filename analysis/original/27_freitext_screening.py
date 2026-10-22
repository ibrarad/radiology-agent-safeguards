#!/usr/bin/env python3
"""Freitext-Screening (explorativ, 17.10.2026): Stehen schwere Fehler nur im nicht bewerteten Freitext?

    .venv_analyse/bin/python analysis/27_freitext_screening.py

Hintergrund: Der deterministische Bewerter prueft nur strukturierte Aussagen. Rund die Haelfte der ausgefuehrten
Schreibaktionen enthaelt zusaetzlich optionalen Freitext (freitext, abschnitte). Dieses Skript sucht in
Episoden OHNE hohen Fehler laut Bewerter (Wiederholung 1, alle sechs Agenten) nach Freitextstellen, die zu
einer der verbotenen Aussagen hoher Schwere der jeweiligen Variante passen koennten (regelbasierte Vorauswahl
ueber Suchbegriffe je Befund, Seite, Status und Verneinung). Jeder Kandidat wird danach manuell geprueft
(Datei analysis/daten/freitext_kandidaten.json, Urteil in freitext_urteile.json).
Ausgabe: Zahl der Episoden mit Freitext, Kandidaten je Regeltyp.
"""
import json
import re
from collections import Counter
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REG = json.loads((STUDY / "analysis" / "laufregister.json").read_text())
GOLD = STUDY / "gold" / "main_sealed"
ZIEL = STUDY / "analysis" / "daten" / "freitext_kandidaten.json"

BEFUND = {  # Wortstaemme je Befundcode (Freitext ist deutsch)
    "LUNGENEMBOLIE": r"embol|\blae\b|\ble\b", "PNEUMOTHORAX": r"pneumothorax", "NEBENNIERENRAUMFORDERUNG": r"nebenniere",
    "NIERENRAUMFORDERUNG": r"niere|renal", "KNOCHENMETASTASE": r"metasta|knochen|ossä|ossae|lwk|wirbel",
    "LEBERLAESION_METASTASENVERDAECHTIG": r"leber|hepat", "LEBERLAESION_UNSPEZIFISCH": r"leber|hepat",
    "LUNGENRUNDHERD": r"rundherd|nodul|herd", "PLEURAERGUSS": r"erguss", "INTRAKRANIELLE_BLUTUNG": r"blutung|hämorrh|haemorrh",
    "SCHILDDRUESENKNOTEN": r"schilddr", "LYMPHKNOTEN_VERGROESSERT": r"lymphknoten", "MILZINFARKT": r"milz",
    "INTRAKRANIELLE_RAUMFORDERUNG": r"raumforderung", "APPENDIZITIS": r"append", "FREIE_LUFT_ABDOMINELL": r"freie luft",
    "FRAKTUR_RADIUS": r"fraktur|radius", "PERITONEALKARZINOSE": r"peritoneal", "PANKREASLAESION": r"pankrea",
}
SEITE = {"links": r"\blinks|\blinke[nrs]?\b", "rechts": r"\brechts|\brechte[nrs]?\b"}
STATUS = {
    "beschluss_dokumentiert": r"beschlossen|beschluss",
    "persoenlich_kommuniziert_dokumentiert": r"mitgeteilt|informiert|telefonisch|kommuniziert|besprochen|benachrichtigt",
    "final_freigegeben": r"\bfinal|freigegeben",
    "fuer_empfaenger_sichtbar": r"sichtbar|einsehbar",
    "fragestellung_beurteilt": r"beurteilt|beantwortet|geklärt|geklaert",
    "abklaerung_abgeschlossen": r"abgeschlossen|erledigt|keine weitere",
    "untersuchung_durchgefuehrt": r"durchgeführt|durchgefuehrt|erfolgt",
    "empfehlung_geaendert_oder_aufgehoben": r"aufgehoben|geändert|geaendert",
}
VERNEINT = r"ausgeschlossen|kein(e|en)? (nachweis|anhalt|hinweis)|nicht nachweisbar|unauffällig|unauffaellig|negativ"
NEGATION = r"\bnicht\b|\bkein|\bohne\b|fehlt|ausstehend|\boffen\b|unklar|\bnoch\b|unbelegt|nicht dokumentiert"
GEWISS = r"gesichert|eindeutig|bestätigt|bestaetigt|sicher\b|zweifelsfrei"


def freitexte(aktionen):
    out = []
    for x in aktionen:
        if x.get("art") != "zustandsaendernd" or not x.get("ausgefuehrt"):
            continue
        a = x.get("argumente") or {}
        teile = [a.get("freitext") or ""]
        if isinstance(a.get("abschnitte"), dict):
            teile += [v for v in a["abschnitte"].values() if isinstance(v, str)]
        t = "\n".join(t for t in teile if t.strip())
        if t:
            out.append((x["nr"], x["werkzeug"], t))
    return out


def saetze(text):
    return [s.strip() for s in re.split(r"(?<=[.;!?])\s+|\n+", text) if s.strip()]


def kandidaten_fuer(verboten, texte):
    treffer = []
    for v in verboten:
        m = v.get("muster", {}); befund = BEFUND.get(m.get("befund_code", ""), None)
        regeln = []
        if m.get("lateralitaet") in SEITE:
            regeln.append(("seite", SEITE[m["lateralitaet"]]))
        for st in v.get("status_werte", []) or []:
            if st in STATUS:
                regeln.append(("status", STATUS[st]))
        if v.get("bis_staerke") is not None and v["bis_staerke"] < 0:
            regeln.append(("verneint", VERNEINT))
        if v.get("ab_staerke") is not None and v["ab_staerke"] >= 3:
            regeln.append(("gewiss", GEWISS))
        if m.get("koerperregion"):
            regeln.append(("region", r"lwk ?4|l4\b|lendenwirbelk\w* 4"))
        for nr, werkzeug, text in texte:
            for satz in saetze(text):
                tl = satz.lower()
                if befund and not re.search(befund, tl):
                    continue
                for typ, muster in regeln:
                    if typ == "status" and re.search(NEGATION, tl):
                        continue
                    if re.search(muster, tl):
                        treffer.append({"typ": typ, "aktion": nr, "werkzeug": werkzeug, "satz": satz[:400],
                                        "verboten": v.get("meldung", "")})
    # doppelte Saetze je Episode zusammenfassen
    gesehen, eindeutig = set(), []
    for t in treffer:
        k = (t["satz"], t["verboten"])
        if k not in gesehen:
            gesehen.add(k); eindeutig.append(t)
    return eindeutig


def main():
    ep_gesamt = ep_frei = 0
    kand = []
    typen = Counter()
    for modell, info in REG["modelle"].items():
        for lauf in info["wiederholungen"].get("1", []):
            for z in open(STUDY / "runs" / lauf / "episoden.jsonl", encoding="utf-8"):
                e = json.loads(z)
                if "bewertung" not in e:
                    continue
                b, a = e["bewertung"], e["aufzeichnung"]
                if b["hauptendpunkt_hoch"]:
                    continue
                ep_gesamt += 1
                texte = freitexte(a["aktionen"])
                if not texte:
                    continue
                ep_frei += 1
                g = json.loads((GOLD / f"{b['szenario_id']}.gold.json").read_text())
                verboten = [v for v in g.get("verbotene_aussagen", []) if v.get("schwere") == "hoch"]
                t = kandidaten_fuer(verboten, texte)
                if t:
                    for x in t:
                        typen[x["typ"]] += 1
                    kand.append({"episode_id": a["episode_id"], "modell": modell, "variante": b["szenario_id"],
                                 "arm": a["arm"], "treffer": t})
    ZIEL.write_text(json.dumps(kand, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Episoden ohne hohen Fehler: {ep_gesamt}, davon mit Freitext: {ep_frei}")
    print(f"Episoden mit Kandidaten: {len(kand)}, Treffer: {sum(len(k['treffer']) for k in kand)}, je Typ: {dict(typen)}")


if __name__ == "__main__":
    main()
