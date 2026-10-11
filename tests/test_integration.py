"""Tests d'intégration avec Home Assistant (nécessite pytest-homeassistant-custom-component)."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.helpers import device_registry as dr  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.labellenergie.api import ApiError, AuthError, LabellenergieClient  # noqa: E402
from custom_components.labellenergie.const import DOMAIN  # noqa: E402

NUMERO = "22497684412005"
NOM = "4 D 4 bd DE CRETEIL, 94100 SAINT-MAUR-DES-FOSSES - 22497684412005"
PDLS = {
    NUMERO: {
        "numero": NUMERO,
        "pdc_contrat_id": "c1",
        "nom": NOM,
        "type_compteur": "Compteur Linky",
        "offre": {
            "puissance": 6.0,
            "abonnement": 15.1266,
            "base": None,
            "hp": 0.189,
            "hc": 0.14676,
            "plagesHc": ["1h04 - 7h04", "14h34 - 16h34"],
            "lastChange": "2026-06-25",
        },
    }
}
PDL_BASE = {
    "numero": "999",
    "pdc_contrat_id": "c2",
    "nom": "Autre adresse - 999",
    "type_compteur": "Compteur Linky",
    "offre": {
        "puissance": 9.0,
        "abonnement": 20.0,
        "base": 0.2,
        "hp": None,
        "hc": None,
        "plagesHc": [],
        "lastChange": "2026-01-01",
    },
}


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


@pytest.fixture
def get_pdls():
    """Remplace l'appel réseau pendant toute la durée du test (y compris les relances à 24 h)."""
    with patch.object(LabellenergieClient, "async_get_pdls", AsyncMock()) as mock:
        yield mock


async def _setup(hass, get_pdls, pdls):
    get_pdls.return_value = pdls
    entry = MockConfigEntry(
        domain=DOMAIN, data={"email": "a@b.fr", "password": "pw"}, unique_id="a@b.fr"
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass, numero, key):
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{numero}_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


async def test_entites_et_appareil(hass, freezer, get_pdls):
    freezer.move_to("2026-10-15T00:30:00+02:00")
    entry = await _setup(hass, get_pdls, deepcopy(PDLS))
    assert entry.state is ConfigEntryState.LOADED

    appareil = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, NUMERO), entry.entry_id
    )
    assert appareil.name == NOM

    assert float(_state(hass, NUMERO, "abonnement").state) == 15.1266
    assert float(_state(hass, NUMERO, "prix_hc").state) == 0.14676
    assert float(_state(hass, NUMERO, "prix_hp").state) == 0.189
    assert _state(hass, NUMERO, "prix_base").state == "unavailable"
    assert _state(hass, NUMERO, "plages_hc").state == "1h04 - 7h04, 14h34 - 16h34"
    assert float(_state(hass, NUMERO, "puissance").state) == 6.0
    assert _state(hass, NUMERO, "derniere_modification").state == "2026-06-25"
    prix = _state(hass, NUMERO, "prix_actuel")
    assert float(prix.state) == 0.189
    assert prix.attributes["unit_of_measurement"] == "EUR/kWh"


async def test_prix_actuel_bascule_aux_heures_de_changement(hass, freezer, get_pdls):
    freezer.move_to("2026-10-15T00:30:00+02:00")
    await _setup(hass, get_pdls, deepcopy(PDLS))
    assert float(_state(hass, NUMERO, "prix_actuel").state) == 0.189

    for instant, prix, creuse in [
        ("2026-10-15T01:04:00+02:00", 0.14676, True),
        ("2026-10-15T07:04:00+02:00", 0.189, False),
        ("2026-10-15T14:34:00+02:00", 0.14676, True),
        ("2026-10-15T16:34:00+02:00", 0.189, False),
        ("2026-10-16T01:04:00+02:00", 0.14676, True),  # lendemain
    ]:
        freezer.move_to(instant)
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        etat = _state(hass, NUMERO, "prix_actuel")
        assert float(etat.state) == prix, instant
        assert etat.attributes["heure_creuse"] is creuse


async def test_offre_base_sans_bascule(hass, freezer, get_pdls):
    freezer.move_to("2026-10-15T00:30:00+02:00")
    await _setup(hass, get_pdls, {"999": deepcopy(PDL_BASE)})
    etat = _state(hass, "999", "prix_actuel")
    assert float(etat.state) == 0.2
    assert etat.attributes["option"] == "base"
    assert _state(hass, "999", "prix_hc").state == "unavailable"


async def test_nouveau_pdl_notifie_et_entites_ajoutees(hass, get_pdls):
    entry = await _setup(hass, get_pdls, deepcopy(PDLS))
    coordinator = entry.runtime_data
    with patch(
        "custom_components.labellenergie.coordinator.persistent_notification.async_create",
        MagicMock(),
    ) as notif:
        get_pdls.return_value = {**deepcopy(PDLS), "999": deepcopy(PDL_BASE)}
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    notif.assert_called_once()
    assert notif.call_args.kwargs["notification_id"] == f"{DOMAIN}_nouveau_pdl_999"
    assert "Autre adresse - 999" in notif.call_args.args[1]
    assert _state(hass, "999", "prix_actuel") is not None


async def test_pas_de_notification_a_la_configuration_initiale(hass, get_pdls):
    with patch(
        "custom_components.labellenergie.coordinator.persistent_notification.async_create",
        MagicMock(),
    ) as notif:
        await _setup(hass, get_pdls, {**deepcopy(PDLS), "999": deepcopy(PDL_BASE)})
    notif.assert_not_called()


async def test_erreur_authentification_declenche_reauth(hass, get_pdls):
    entry = MockConfigEntry(domain=DOMAIN, data={"email": "a@b.fr", "password": "pw"})
    entry.add_to_hass(hass)
    get_pdls.side_effect = AuthError
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(hass.config_entries.flow.async_progress_by_handler(DOMAIN))


async def test_config_flow_ok(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    with (
        patch.object(LabellenergieClient, "async_login", AsyncMock()),
        patch("custom_components.labellenergie.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": "Marc@Exemple.fr", "password": "x"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"email": "Marc@Exemple.fr", "password": "x"}
    assert result["result"].unique_id == "marc@exemple.fr"


@pytest.mark.parametrize(
    ("erreur", "cle"),
    [(AuthError, "invalid_auth"), (ApiError, "cannot_connect"), (RuntimeError, "unknown")],
)
async def test_config_flow_erreurs(hass, erreur, cle):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch.object(LabellenergieClient, "async_login", AsyncMock(side_effect=erreur)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": "a@b.fr", "password": "x"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": cle}
