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
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import LabellenergieConfigEntry, LabellenergieCoordinator
from .entity import (
    LabellenergieBasculeEntity,
    LabellenergieEntity,
    ajouter_entites_par_pdl,
)
from .factures import (
    TIMEZONE,
    Facture,
    debut_mois_utc,
    total_annee,
    total_glissant,
)
from .pricing import prix_actuel
from .statistiques import async_backfill

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


def _mois(mois: date) -> str:
    return mois.strftime("%Y-%m")


@dataclass(frozen=True, kw_only=True)
class LabellenergieFactureDescription(SensorEntityDescription):
    """Capteur calculé à partir de l'historique de facturation."""

    value_fn: Callable[[list[Facture], int], float | None]
    attrs_fn: Callable[[list[Facture]], dict[str, Any]] | None = None
    last_reset_fn: Callable[[list[Facture]], datetime] | None = None
    # Importe l'historique dans les statistiques : "mensuel" ou "cumul".
    backfill: str | None = None


_FACTURE = {
    "device_class": SensorDeviceClass.MONETARY,
    "native_unit_of_measurement": UNITE_EUR,
    "suggested_display_precision": 2,
}

SENSORS_FACTURES: tuple[LabellenergieFactureDescription, ...] = (
    LabellenergieFactureDescription(
        key="total_ttc",
        translation_key="total_ttc",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda f, _annee: f[-1].total_ttc,
        attrs_fn=lambda f: {"mois": _mois(f[-1].mois), "total_ht": f[-1].total_ht},
        last_reset_fn=lambda f: debut_mois_utc(f[-1].mois),
        backfill="mensuel",
        **_FACTURE,
    ),
    LabellenergieFactureDescription(
        key="cumulative_total_ttc",
        translation_key="cumulative_total_ttc",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda f, _annee: f[-1].cumul,
        attrs_fn=lambda f: {"depuis": _mois(f[0].mois)},
        backfill="cumul",
        **_FACTURE,
    ),
    LabellenergieFactureDescription(
        key="total_annee_passee",
        translation_key="total_annee_passee",
        value_fn=lambda f, annee: total_annee(f, annee - 1),
        **_FACTURE,
    ),
    LabellenergieFactureDescription(
        key="total_annee_en_cours",
        translation_key="total_annee_en_cours",
        value_fn=lambda f, annee: total_annee(f, annee) or 0.0,
        **_FACTURE,
    ),
    LabellenergieFactureDescription(
        key="total_annee_glissante",
        translation_key="total_annee_glissante",
        value_fn=lambda f, _annee: total_glissant(f)[0],
        attrs_fn=lambda f: {
            "mois_debut": _mois(total_glissant(f)[1]),
            "mois_fin": _mois(total_glissant(f)[2]),
        },
        **_FACTURE,
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
            *(LabellenergieFacture(coordinator, numero, d) for d in SENSORS_FACTURES),
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


class LabellenergieFacture(LabellenergieEntity, SensorEntity):
    """Montants payés, calculés sur l'historique des factures mensuelles."""

    entity_description: LabellenergieFactureDescription
    _backfill_demande = False

    @property
    def _factures(self) -> list[Facture]:
        pdl = self._pdl
        return (pdl.get("factures") if pdl else None) or []

    @property
    def native_value(self) -> float | None:
        factures = self._factures
        if not factures:
            return None
        annee = dt_util.now().astimezone(TIMEZONE).year
        return self.entity_description.value_fn(factures, annee)

    @property
    def _a_une_valeur(self) -> bool:
        return self.native_value is not None

    @property
    def last_reset(self) -> datetime | None:
        fn = self.entity_description.last_reset_fn
        factures = self._factures
        return fn(factures) if fn and factures else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        factures = self._factures
        return fn(factures) if fn and factures and self.native_value is not None else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_backfill()

    @callback
    def _handle_coordinator_update(self) -> None:
        # Les factures ont pu manquer au démarrage (erreur réseau) : on réessaie.
        if not self._backfill_demande:
            self.hass.async_create_task(self._async_backfill())
        super()._handle_coordinator_update()

    async def _async_backfill(self) -> None:
        mode = self.entity_description.backfill
        factures = self._factures
        if mode is None or not factures or self._backfill_demande:
            return
        self._backfill_demande = True
        await async_backfill(
            self.hass, self.entity_id, factures, cumulatif=mode == "cumul"
        )
