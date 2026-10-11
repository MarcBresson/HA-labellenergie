"""Capteurs : un jeu d'entités par point de livraison."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER
from .coordinator import LabellenergieConfigEntry, LabellenergieCoordinator
from .pricing import parse_plages_hc, prix_actuel, prochain_changement

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
    """Crée les entités, y compris pour les PDL qui apparaîtront plus tard."""
    coordinator = entry.runtime_data
    connus: set[str] = set()

    @callback
    def _ajouter_nouveaux_pdl() -> None:
        entites: list[LabellenergieEntity] = []
        for numero in coordinator.data:
            if numero in connus:
                continue
            connus.add(numero)
            entites.extend(
                LabellenergieSensor(coordinator, numero, description)
                for description in SENSORS
            )
            entites.extend(
                LabellenergiePdlSensor(coordinator, numero, description)
                for description in SENSORS_PDL
            )
            entites.append(LabellenergiePrixActuel(coordinator, numero, PRIX_ACTUEL))
        if entites:
            async_add_entities(entites)

    _ajouter_nouveaux_pdl()
    entry.async_on_unload(coordinator.async_add_listener(_ajouter_nouveaux_pdl))


class LabellenergieEntity(CoordinatorEntity[LabellenergieCoordinator], SensorEntity):
    """Entité rattachée à un appareil = un point de livraison."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LabellenergieCoordinator,
        numero: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._numero = numero
        pdl = coordinator.data[numero]
        self._attr_unique_id = f"{numero}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, numero)},
            name=pdl["nom"],
            manufacturer=MANUFACTURER,
            model=pdl.get("type_compteur"),
        )

    @property
    def _pdl(self) -> dict[str, Any] | None:
        return self.coordinator.data.get(self._numero)

    @property
    def _offre(self) -> dict[str, Any]:
        pdl = self._pdl
        return pdl["offre"] if pdl else {}

    @property
    def available(self) -> bool:
        # Valeur null côté API (ex. prix HC sur une offre base) : entité indisponible.
        return super().available and self._pdl is not None and self.native_value is not None


class LabellenergieSensor(LabellenergieEntity):
    """Valeur lue dans `offreCourante`."""

    entity_description: LabellenergieSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._offre)

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


class LabellenergiePrixActuel(LabellenergieEntity):
    """Prix du kWh en vigueur, recalculé uniquement aux bascules HC/HP."""

    _unsub_bascule: CALLBACK_TYPE | None = None

    @property
    def native_value(self) -> float | None:
        if self._pdl is None:
            return None
        return prix_actuel(self._offre, dt_util.now()).prix

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._pdl is None:
            return None
        courant = prix_actuel(self._offre, dt_util.now())
        return {"heure_creuse": courant.heure_creuse, "option": courant.option}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._annuler_bascule)
        self._planifier_bascule()

    @callback
    def _handle_coordinator_update(self) -> None:
        # Plages ou offre modifiées : la prochaine bascule a pu changer.
        self._planifier_bascule()
        super()._handle_coordinator_update()

    @callback
    def _annuler_bascule(self) -> None:
        if self._unsub_bascule is not None:
            self._unsub_bascule()
            self._unsub_bascule = None

    @callback
    def _planifier_bascule(self) -> None:
        self._annuler_bascule()
        offre = self._offre
        if offre.get("base") is not None:
            return  # prix unique : aucune bascule
        quand = prochain_changement(parse_plages_hc(offre.get("plagesHc")), dt_util.now())
        if quand is not None:
            self._unsub_bascule = async_track_point_in_time(
                self.hass, self._bascule, quand
            )

    @callback
    def _bascule(self, _maintenant: datetime) -> None:
        self._unsub_bascule = None
        self._planifier_bascule()
        self.async_write_ha_state()
