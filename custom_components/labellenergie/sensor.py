"""Capteurs : un jeu d'entités par point de livraison."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import LabellenergieConfigEntry, LabellenergieCoordinator
from .entity import (
    LabellenergieBasculeEntity,
    LabellenergieEntity,
    ajouter_entites_par_pdl,
)
from .pricing import prix_actuel

UNITE_EUR = "EUR"
UNITE_EUR_KWH = f"{UNITE_EUR}/{UnitOfEnergy.KILO_WATT_HOUR}"


def _date(valeur: str | None) -> date | None:
    try:
        return date.fromisoformat(valeur) if valeur else None
    except ValueError:
        return None


def _plages(offre: dict[str, Any]) -> str | None:
    plages = offre.get("plagesHc")
    return ", ".join(plages) if plages else None


@dataclass(frozen=True, kw_only=True)
class LabellenergieSensorDescription(SensorEntityDescription):
    """Capteur lu directement dans `offreCourante`."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[LabellenergieSensorDescription, ...] = (
    LabellenergieSensorDescription(
        key="abonnement",
        translation_key="abonnement",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=UNITE_EUR,
        suggested_display_precision=2,
        value_fn=lambda offre: offre.get("abonnement"),
    ),
    LabellenergieSensorDescription(
        key="prix_hc",
        translation_key="prix_hc",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UNITE_EUR_KWH,
        suggested_display_precision=5,
        value_fn=lambda offre: offre.get("hc"),
    ),
    LabellenergieSensorDescription(
        key="prix_hp",
        translation_key="prix_hp",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UNITE_EUR_KWH,
        suggested_display_precision=5,
        value_fn=lambda offre: offre.get("hp"),
    ),
    LabellenergieSensorDescription(
        key="prix_base",
        translation_key="prix_base",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UNITE_EUR_KWH,
        suggested_display_precision=5,
        value_fn=lambda offre: offre.get("base"),
    ),
    LabellenergieSensorDescription(
        key="plages_hc",
        translation_key="plages_hc",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_plages,
        attrs_fn=lambda offre: {"plages": offre.get("plagesHc") or []},
    ),
    LabellenergieSensorDescription(
        key="puissance",
        translation_key="puissance",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="kVA",
        value_fn=lambda offre: offre.get("puissance"),
    ),
    LabellenergieSensorDescription(
        key="derniere_modification",
        translation_key="derniere_modification",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda offre: _date(offre.get("lastChange")),
    ),
)

# Identité du point de livraison (lue dans le PDL, pas dans l'offre).
SENSORS_PDL: tuple[LabellenergieSensorDescription, ...] = (
    LabellenergieSensorDescription(
        key="numero_pdl",
        translation_key="numero_pdl",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda pdl: pdl.get("numero"),
    ),
    LabellenergieSensorDescription(
        key="adresse",
        translation_key="adresse",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda pdl: pdl.get("adresse") or None,
    ),
)

PRIX_ACTUEL = SensorEntityDescription(
    key="prix_actuel",
    translation_key="prix_actuel",
    native_unit_of_measurement=UNITE_EUR_KWH,
    suggested_display_precision=5,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LabellenergieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crée les capteurs de chaque point de livraison."""

    def _creer(coordinator: LabellenergieCoordinator, numero: str) -> list[Entity]:
        return [
            *(LabellenergieSensor(coordinator, numero, d) for d in SENSORS),
            *(LabellenergiePdlSensor(coordinator, numero, d) for d in SENSORS_PDL),
            LabellenergiePrixActuel(coordinator, numero, PRIX_ACTUEL),
        ]

    ajouter_entites_par_pdl(entry, async_add_entities, _creer)


class LabellenergieSensor(LabellenergieEntity, SensorEntity):
    """Valeur lue dans `offreCourante`."""

    entity_description: LabellenergieSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._offre)

    @property
    def _a_une_valeur(self) -> bool:
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs_fn = self.entity_description.attrs_fn
        return attrs_fn(self._offre) if attrs_fn else None


class LabellenergiePdlSensor(LabellenergieSensor):
    """Valeur lue dans le PDL lui-même (numéro, adresse)."""

    @property
    def native_value(self) -> Any:
        pdl = self._pdl
        return self.entity_description.value_fn(pdl) if pdl else None


class LabellenergiePrixActuel(LabellenergieBasculeEntity, SensorEntity):
    """Prix du kWh en vigueur, recalculé uniquement aux bascules HC/HP."""

    @property
    def native_value(self) -> float | None:
        if self._pdl is None:
            return None
        return prix_actuel(self._offre, dt_util.now()).prix

    @property
    def _a_une_valeur(self) -> bool:
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._pdl is None:
            return None
        courant = prix_actuel(self._offre, dt_util.now())
        return {"heure_creuse": courant.heure_creuse, "option": courant.option}
