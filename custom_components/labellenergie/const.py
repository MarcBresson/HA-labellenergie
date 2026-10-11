"""Constantes de l'intégration La Belle Énergie."""

from datetime import timedelta

DOMAIN = "labellenergie"

MANUFACTURER = "La Belle Énergie"

BASE_URL = "https://espace-client.labellenergie.fr"
API_LOGIN = "/portail/api/custom-token-auth"
API_LISTE_PDL = "/portail/api/v2/espace-client-liste-pdl"
API_INFOS_PDL = "/portail/api/v2/espace-client-pdl-infos"

USER_AGENT = "Mozilla/5.0 (compatible; HomeAssistant-labellenergie/0.1)"

# Les tarifs changent rarement ; le prix actuel (HC/HP) est recalculé localement.
UPDATE_INTERVAL = timedelta(hours=24)
