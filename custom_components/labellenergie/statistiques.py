"""Backfill de l'historique de facturation dans les statistiques de l'enregistreur."""

from __future__ import annotations

import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.core import HomeAssistant

from .factures import Facture, debut_mois_utc

_LOGGER = logging.getLogger(__name__)

UNITE = "EUR"


async def async_backfill(
    hass: HomeAssistant,
    entity_id: str,
    factures: list[Facture],
    *,
    cumulatif: bool,
) -> bool:
    """Importe un point par mois dans les statistiques de l'entité.

    N'agit qu'une fois : dès que l'entité a des statistiques, l'enregistreur
    compile lui-même les mois suivants à partir de son état, et réimporter
    écraserait des lignes déjà compilées avec des sommes incohérentes.
    Renvoie vrai si un import a été demandé.
    """
    if not factures:
        return False

    deja = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, entity_id, False, {"sum"}
    )
    if deja.get(entity_id):
        return False

    metadata = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=None,
        source="recorder",
        statistic_id=entity_id,
        unit_class=None,
        unit_of_measurement=UNITE,
    )
    statistiques: list[StatisticData] = []
    for facture in factures:
        debut = debut_mois_utc(facture.mois)
        if cumulatif:
            statistiques.append(
                StatisticData(start=debut, state=facture.cumul, sum=facture.cumul)
            )
        else:
            statistiques.append(
                StatisticData(
                    start=debut,
                    state=facture.total_ttc,
                    sum=facture.cumul,
                    last_reset=debut,
                )
            )
    async_import_statistics(hass, metadata, statistiques)
    _LOGGER.debug("%s : %s mois importés", entity_id, len(statistiques))
    return True
