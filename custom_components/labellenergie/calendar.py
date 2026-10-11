"""Calendrier des heures creuses : une période d'événement par plage horaire."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityDescription,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import LabellenergieConfigEntry, LabellenergieCoordinator
from .entity import LabellenergieBasculeEntity, ajouter_entites_par_pdl
from .pricing import parse_plages_hc, plages_creuses

CALENDRIER_HC = CalendarEntityDescription(key="calendrier_hc", translation_key="calendrier_hc")
RESUME = "Heures creuses"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LabellenergieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crée le calendrier des heures creuses de chaque point de livraison."""

    def _creer(coordinator: LabellenergieCoordinator, numero: str) -> list[Entity]:
        return [LabellenergieCalendrier(coordinator, numero, CALENDRIER_HC)]

    ajouter_entites_par_pdl(entry, async_add_entities, _creer)


class LabellenergieCalendrier(LabellenergieBasculeEntity, CalendarEntity):
    """Événement « Heures creuses » pour chaque plage ; actif pendant les heures creuses."""

    @property
    def _a_une_valeur(self) -> bool:
        offre = self._offre
        return offre.get("base") is None and bool(parse_plages_hc(offre.get("plagesHc")))

    def _evenements(self, debut: datetime, fin: datetime) -> list[CalendarEvent]:
        plages = parse_plages_hc(self._offre.get("plagesHc"))
        if self._offre.get("base") is not None:
            return []
        return [
            CalendarEvent(start=d, end=f, summary=RESUME)
            for d, f in plages_creuses(plages, debut, fin)
        ]

    @property
    def event(self) -> CalendarEvent | None:
        """Période en cours, sinon la prochaine."""
        maintenant = dt_util.now()
        evenements = self._evenements(maintenant, maintenant + timedelta(days=2))
        return evenements[0] if evenements else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._evenements(start_date, end_date)
