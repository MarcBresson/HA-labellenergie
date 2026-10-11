"""Base commune des entités : rattachement à l'appareil du point de livraison."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER
from .coordinator import LabellenergieConfigEntry, LabellenergieCoordinator
from .pricing import parse_plages_hc, prochain_changement


def ajouter_entites_par_pdl(
    entry: LabellenergieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    creer: Callable[[LabellenergieCoordinator, str], list[Entity]],
) -> None:
    """Crée les entités de chaque PDL, y compris ceux qui apparaîtront plus tard."""
    coordinator = entry.runtime_data
    connus: set[str] = set()

    @callback
    def _ajouter_nouveaux_pdl() -> None:
        entites: list[Entity] = []
        for numero in coordinator.data:
            if numero not in connus:
                connus.add(numero)
                entites.extend(creer(coordinator, numero))
        if entites:
            async_add_entities(entites)

    _ajouter_nouveaux_pdl()
    entry.async_on_unload(coordinator.async_add_listener(_ajouter_nouveaux_pdl))


class LabellenergieEntity(CoordinatorEntity[LabellenergieCoordinator]):
    """Entité rattachée à un appareil = un point de livraison."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LabellenergieCoordinator,
        numero: str,
        description: EntityDescription,
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
    def _a_une_valeur(self) -> bool:
        """Faux si l'offre n'a pas cette donnée (ex. prix HC sur une offre base)."""
        return True

    @property
    def available(self) -> bool:
        return super().available and self._pdl is not None and self._a_une_valeur


class LabellenergieBasculeEntity(LabellenergieEntity):
    """Entité qui dépend de l'instant : réécrite uniquement aux bascules HC ↔ HP."""

    _unsub_bascule: CALLBACK_TYPE | None = None

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
    def _bascule(self, _maintenant: Any) -> None:
        self._unsub_bascule = None
        self._planifier_bascule()
        self.async_write_ha_state()

