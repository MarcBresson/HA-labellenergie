"""Coordinateur de mise à jour des tarifs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthError, LabellenergieClient
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type LabellenergieConfigEntry = ConfigEntry[LabellenergieCoordinator]


class LabellenergieCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Récupère les PDL et leur offre courante (données indexées par numéro de PDL)."""

    config_entry: LabellenergieConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: LabellenergieConfigEntry,
        client: LabellenergieClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            pdls = await self.client.async_get_pdls()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ApiError as err:
            raise UpdateFailed(str(err)) from err

        self._notifier_nouveaux_pdl(pdls)
        return pdls

    def _notifier_nouveaux_pdl(self, pdls: dict[str, dict[str, Any]]) -> None:
        """Notification pour chaque PDL qui n'a pas encore d'appareil.

        Rien n'est envoyé à la configuration initiale (aucun appareil enregistré
        pour cette entrée), ni pour un PDL déjà connu après un redémarrage.
        """
        registre = dr.async_get(self.hass)
        connus = {
            identifiant[1]
            for appareil in dr.async_entries_for_config_entry(
                registre, self.config_entry.entry_id
            )
            for identifiant in appareil.identifiers
            if identifiant[0] == DOMAIN
        }
        if not connus:
            return
        for numero, pdl in pdls.items():
            if numero in connus:
                continue
            persistent_notification.async_create(
                self.hass,
                f"Nouveau point de livraison détecté : {pdl['nom']}. "
                "Ses entités ont été ajoutées automatiquement.",
                title="La Belle Énergie : nouveau point de livraison",
                notification_id=f"{DOMAIN}_nouveau_pdl_{numero}",
            )
