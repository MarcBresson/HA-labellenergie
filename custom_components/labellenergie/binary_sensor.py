"""Capteur binaire : heure creuse en cours."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import LabellenergieConfigEntry, LabellenergieCoordinator
from .entity import LabellenergieBasculeEntity, ajouter_entites_par_pdl
from .pricing import prix_actuel

HEURE_CREUSE = BinarySensorEntityDescription(
    key="heure_creuse", translation_key="heure_creuse"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LabellenergieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crée le capteur « heure creuse en cours » de chaque point de livraison."""

    def _creer(coordinator: LabellenergieCoordinator, numero: str) -> list[Entity]:
        return [LabellenergieHeureCreuse(coordinator, numero, HEURE_CREUSE)]

    ajouter_entites_par_pdl(entry, async_add_entities, _creer)


class LabellenergieHeureCreuse(LabellenergieBasculeEntity, BinarySensorEntity):
    """Actif pendant les heures creuses ; indisponible pour une offre Base."""

    @property
    def is_on(self) -> bool | None:
        if self._pdl is None:
            return None
        return prix_actuel(self._offre, dt_util.now()).heure_creuse

    @property
    def _a_une_valeur(self) -> bool:
        return self.is_on is not None
