"""Geschichtete Zufallsstichprobe fuer das aerztliche Episodenaudit.

Kernanforderungen, die hier umgesetzt sind:
  - Schichtung ueber Modul, Arm, Modell und Bedingung;
  - EINSCHLUSS der Episoden, die der automatische Bewerter als unauffaellig eingestuft hat -
    ohne sie liesse sich nur messen, wie oft der Bewerter zu Unrecht anschlaegt, nicht wie
    oft er etwas uebersieht;
  - Speicherung der Ziehungswahrscheinlichkeit je Episode;
  - Maskierung von Arm, Modell und Kennungen fuer die verblindete Bewertung, ohne
    entscheidungsrelevante Information zu entfernen;
  - getrennte Kennzeichnung von Episoden, die wegen Auffaelligkeit zusaetzlich geprueft
    werden ("Auffaelligkeitszusatz"), damit sie die Schaetzung nicht verzerren.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any

SCHICHTFELDER = ("modul", "arm", "modellkennung", "bedingung")


@dataclass
class Auditeintrag:
    audit_id: str
    episode_id: str
    schicht: tuple[str, ...]
    ziehungswahrscheinlichkeit: float
    grund: str                      # "geschichtete_zufallsziehung" | "auffaelligkeitszusatz"
    bewerter_auffaellig: bool       # was der automatische Bewerter gefunden hat

    def als_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id, "episode_id": self.episode_id,
            "schicht": dict(zip(SCHICHTFELDER, self.schicht)),
            "ziehungswahrscheinlichkeit": round(self.ziehungswahrscheinlichkeit, 6),
            "grund": self.grund, "bewerter_auffaellig": self.bewerter_auffaellig,
        }


@dataclass
class Auditstichprobe:
    eintraege: list[Auditeintrag] = field(default_factory=list)
    schichtgroessen: dict[tuple[str, ...], int] = field(default_factory=dict)
    seed: int = 0

    def als_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "schichten": [{"schicht": dict(zip(SCHICHTFELDER, k)), "umfang": v,
                           "gezogen": sum(1 for e in self.eintraege if e.schicht == k)}
                          for k, v in sorted(self.schichtgroessen.items())],
            "eintraege": [e.als_dict() for e in self.eintraege],
        }


def _schicht(bewertung: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(bewertung.get(f, "")) for f in SCHICHTFELDER)


def ziehe(bewertungen: list[dict[str, Any]], umfang: int, seed: int,
          auffaellige_zusatzquote: float = 0.0) -> Auditstichprobe:
    """Zieht eine nach Modul, Arm, Modell und Bedingung geschichtete Zufallsstichprobe.

    Der Umfang wird proportional auf die Schichten verteilt; jede besetzte Schicht erhaelt
    mindestens eine Episode, damit keine Kombination voellig unbeobachtet bleibt.
    """
    if umfang <= 0:
        raise ValueError("Umfang muss positiv sein")
    rng = random.Random(seed)

    nach_schicht: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for b in bewertungen:
        nach_schicht.setdefault(_schicht(b), []).append(b)
    gesamt = len(bewertungen)
    if umfang > gesamt:
        umfang = gesamt

    # Proportionale Zuteilung mit Mindestbelegung 1 je besetzter Schicht.
    zuteilung: dict[tuple[str, ...], int] = {k: 1 for k in nach_schicht}
    rest = umfang - len(zuteilung)
    if rest < 0:
        # Mehr Schichten als Episoden gewuenscht: Schichten zufaellig auswaehlen.
        gewaehlt = rng.sample(sorted(nach_schicht), umfang)
        zuteilung = {k: 1 for k in gewaehlt}
        rest = 0
    else:
        anteile = sorted(nach_schicht, key=lambda k: -len(nach_schicht[k]))
        i = 0
        while rest > 0:
            k = anteile[i % len(anteile)]
            if zuteilung[k] < len(nach_schicht[k]):
                zuteilung[k] += 1
                rest -= 1
            i += 1
            if i > 10000:
                break

    probe = Auditstichprobe(seed=seed,
                            schichtgroessen={k: len(v) for k, v in nach_schicht.items()})
    for k, n in sorted(zuteilung.items()):
        kandidaten = nach_schicht[k]
        n = min(n, len(kandidaten))
        gezogen = rng.sample(kandidaten, n)
        p = n / len(kandidaten)
        for b in gezogen:
            probe.eintraege.append(Auditeintrag(
                audit_id=_audit_id(b["episode_id"], seed),
                episode_id=b["episode_id"], schicht=k,
                ziehungswahrscheinlichkeit=p, grund="geschichtete_zufallsziehung",
                bewerter_auffaellig=bool(b.get("primaerer_sicherheitsendpunkt"))))

    # Zusaetzliche Prüfung auffaelliger Episoden - getrennt gekennzeichnet, damit sie
    # die Schaetzung der Uebereinstimmung nicht verzerren.
    if auffaellige_zusatzquote > 0:
        bereits = {e.episode_id for e in probe.eintraege}
        auffaellig = [b for b in bewertungen
                      if b.get("primaerer_sicherheitsendpunkt") and b["episode_id"] not in bereits]
        n = int(len(auffaellig) * auffaellige_zusatzquote)
        for b in rng.sample(auffaellig, min(n, len(auffaellig))):
            probe.eintraege.append(Auditeintrag(
                audit_id=_audit_id(b["episode_id"], seed),
                episode_id=b["episode_id"], schicht=_schicht(b),
                ziehungswahrscheinlichkeit=auffaellige_zusatzquote,
                grund="auffaelligkeitszusatz", bewerter_auffaellig=True))
    return probe


def _audit_id(episode_id: str, seed: int) -> str:
    """Neutrale Kennung, aus der sich Arm und Modell nicht ablesen lassen."""
    h = hashlib.sha256(f"{seed}|{episode_id}".encode()).hexdigest()[:8]
    return f"AUD-{h}"


# --------------------------------------------------------------------------- Maskierung

MASKIERTE_FELDER = ("arm", "modellkennung", "episode_id", "szenario_id", "familie_id",
                    "agent_kennung", "pruefer_kennung")


def maskiere(aufzeichnung: dict[str, Any], audit_id: str) -> dict[str, Any]:
    """Entfernt Arm-, Modell- und Kennungsangaben, laesst den klinischen Inhalt unangetastet.

    Maskiert werden ausschliesslich Identifikatoren, NICHT entscheidungsrelevante
    Informationen: Dokumente, Ereignisse, Aktionen, gespeicherte Aussagen und der
    Zustandsverlauf bleiben vollstaendig erhalten.
    """
    aus = {k: v for k, v in aufzeichnung.items() if k not in MASKIERTE_FELDER}
    aus["audit_id"] = audit_id
    # Die Rueckmeldungen der Schutzschicht verraten den Arm ueber die Pruefcodes.
    aktionen = []
    for a in aufzeichnung.get("aktionen", []):
        a = dict(a)
        a.pop("schutzentscheidung", None)
        aktionen.append(a)
    aus["aktionen"] = aktionen
    aus["hinweis"] = ("Arm, Modell und Kennungen sind maskiert. Der klinische Inhalt ist "
                      "vollstaendig erhalten.")
    return aus
