"""Intégration La Belle Énergie : tarifs de l'électricité par point de livraison."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LabellenergieClient
from .coordinator import LabellenergieConfigEntry, LabellenergieCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: LabellenergieConfigEntry) -> bool:
    """Initialise l'intégration à partir d'une entrée de configuration."""
    client = LabellenergieClient(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
    coordinator = LabellenergieCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LabellenergieConfigEntry) -> bool:
    """Décharge l'entrée de configuration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
