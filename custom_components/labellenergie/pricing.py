"""Logique de tarification (heures creuses / heures pleines), sans dépendance à Home Assistant."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

# Les plages horaires du compteur Linky sont exprimées en heure française.
TIMEZONE = ZoneInfo("Europe/Paris")

_MINUTES_PAR_JOUR = 24 * 60
_PLAGE_RE = re.compile(r"(\d{1,2})\s*h\s*(\d{2})?\s*-\s*(\d{1,2})\s*h\s*(\d{2})?")

# (début, fin) en minutes depuis minuit ; la fin est exclue ; début > fin = passe minuit.
Plage = tuple[int, int]


class PrixActuel(NamedTuple):
    """Prix du kWh en vigueur à un instant donné."""

    prix: float | None
    heure_creuse: bool | None  # None pour une offre base
    option: str  # "base" ou "hp_hc"


def parse_plages_hc(plages: list[str] | None) -> list[Plage]:
    """Convertit ["1h04 - 7h04", "14h34 - 16h34"] en minutes depuis minuit."""
    resultat: list[Plage] = []
    for texte in plages or []:
        match = _PLAGE_RE.search(str(texte))
        if not match:
            continue
        h_debut, m_debut, h_fin, m_fin = match.groups()
        debut = int(h_debut) * 60 + int(m_debut or 0)
        fin = int(h_fin) * 60 + int(m_fin or 0)
        if debut > _MINUTES_PAR_JOUR or fin > _MINUTES_PAR_JOUR:
            continue
        resultat.append((debut, fin))
    return resultat


def _minute_creuse(minute: int, plages: list[Plage]) -> bool:
    for debut, fin in plages:
        if debut < fin:
            if debut <= minute < fin:
                return True
        elif debut > fin and (minute >= debut or minute < fin):
            return True
    return False


def _minute_du_jour(instant: datetime) -> int:
    return instant.hour * 60 + instant.minute


def is_heure_creuse(now: datetime, plages: list[Plage]) -> bool:
    """Indique si `now` (datetime avec fuseau) tombe dans une plage d'heures creuses."""
    return _minute_creuse(_minute_du_jour(now.astimezone(TIMEZONE)), plages)


def prochain_changement(plages: list[Plage], now: datetime) -> datetime | None:
    """Prochain instant (strictement après `now`) où l'on passe de HC à HP ou inversement.

    Les plages jointives (ex. 22h-2h puis 2h-6h) ne produisent pas de changement.
    Retourne None s'il n'y a aucune bascule (pas de plage, ou HC toute la journée).
    """
    local = now.astimezone(TIMEZONE).replace(second=0, microsecond=0)
    for delta in range(1, _MINUTES_PAR_JOUR + 1):
        candidat = local + timedelta(minutes=delta)
        minute = _minute_du_jour(candidat)
        precedente = (minute - 1) % _MINUTES_PAR_JOUR
        if _minute_creuse(minute, plages) != _minute_creuse(precedente, plages):
            return candidat
    return None


def prix_actuel(offre: dict[str, Any], now: datetime) -> PrixActuel:
    """Prix du kWh TTC : base si défini, sinon HC dans une plage d'heures creuses, sinon HP."""
    base = offre.get("base")
    if base is not None:
        return PrixActuel(base, None, "base")

    creuse = is_heure_creuse(now, parse_plages_hc(offre.get("plagesHc")))
    hc, hp = offre.get("hc"), offre.get("hp")
    prix = hc if creuse else hp
    if prix is None:
        prix = hp if creuse else hc
    return PrixActuel(prix, creuse, "hp_hc")
