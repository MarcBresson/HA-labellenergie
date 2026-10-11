"""Client de l'espace client La Belle Énergie (sans dépendance à Home Assistant)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_INFOS_PDL,
    API_LISTE_PDL,
    API_LOGIN,
    BASE_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/espace-client/accueil",
}
_DEFAULT_TOKEN_TTL = 600  # secondes (Max-Age observé sur access_token)
_TOKEN_MARGIN = 60
_MAX_PAGES = 20


class LabellenergieError(Exception):
    """Erreur de base."""


class AuthError(LabellenergieError):
    """Identifiants refusés."""


class ApiError(LabellenergieError):
    """Erreur réseau ou réponse inattendue."""


def format_adresse(adresse: dict[str, Any]) -> str:
    """« {complement} {numeroEtRue}, {codePostal} {ville} »."""
    rue = " ".join(
        part for part in (adresse.get("complement"), adresse.get("numeroEtRue")) if part
    )
    ville = " ".join(
        part for part in (adresse.get("codePostal"), adresse.get("ville")) if part
    )
    return ", ".join(part for part in (rue, ville) if part)


class LabellenergieClient:
    """Client HTTP : connexion par cookie `access_token` (valable 10 minutes)."""

    def __init__(
        self, session: aiohttp.ClientSession, email: str, password: str
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._token_expiry = 0.0
        self._lock = asyncio.Lock()

    async def async_login(self) -> None:
        """Se connecte (lève AuthError si les identifiants sont refusés)."""
        async with self._lock:
            await self._login()

    async def _login(self) -> None:
        payload = {
            "isFirstConnection": False,
            "username": self._email,
            "password": self._password,
        }
        try:
            async with self._session.post(
                f"{BASE_URL}{API_LOGIN}",
                json=payload,
                headers={**_HEADERS, "Referer": f"{BASE_URL}/login"},
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (400, 401, 403):
                    raise AuthError("Identifiants refusés")
                if resp.status >= 400:
                    raise ApiError(f"Connexion : HTTP {resp.status}")
                cookie = resp.cookies.get("access_token")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ApiError(f"Connexion impossible : {err}") from err

        if cookie is None or not cookie.value:
            raise ApiError("Connexion : cookie access_token absent de la réponse")

        try:
            ttl = int(cookie["max-age"])
        except (KeyError, ValueError):
            ttl = _DEFAULT_TOKEN_TTL
        self._token = cookie.value
        self._token_expiry = time.monotonic() + max(ttl - _TOKEN_MARGIN, 0)

    async def _async_get_token(self, force: bool = False) -> str:
        async with self._lock:
            if force or self._token is None or time.monotonic() >= self._token_expiry:
                await self._login()
            assert self._token is not None
            return self._token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
    ) -> Any:
        """Appel authentifié ; une reconnexion est tentée si le jeton est refusé."""
        for attempt in (1, 2):
            token = await self._async_get_token(force=attempt == 2)
            try:
                async with self._session.request(
                    method,
                    f"{BASE_URL}{path}",
                    params=params,
                    data=data,
                    headers={**_HEADERS, "Cookie": f"access_token={token}"},
                    timeout=_TIMEOUT,
                ) as resp:
                    if resp.status in (401, 403):
                        if attempt == 1:
                            continue
                        raise AuthError("Jeton refusé après reconnexion")
                    if resp.status >= 400:
                        raise ApiError(f"{path} : HTTP {resp.status}")
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                raise ApiError(f"{path} : {err}") from err
        raise ApiError(f"{path} : échec")  # pragma: no cover

    async def _async_liste_pdl(self) -> list[dict[str, Any]]:
        """Tous les PDL du compte (en suivant la pagination si nécessaire)."""
        data = await self._request("GET", API_LISTE_PDL)
        pdls: list[dict[str, Any]] = list(data.get("pdls") or [])
        total = data.get("total_pdls_count") or len(pdls)

        page = 1
        while len(pdls) < total and page < _MAX_PAGES:
            suite = await self._request("GET", API_LISTE_PDL, params={"page": page})
            connus = {pdl["id"] for pdl in pdls}
            nouveaux = [p for p in suite.get("pdls") or [] if p["id"] not in connus]
            if not nouveaux:
                _LOGGER.warning(
                    "Pagination des PDL : %s sur %s récupérés", len(pdls), total
                )
                break
            pdls.extend(nouveaux)
            page += 1
        return pdls

    async def async_get_pdls(self) -> dict[str, dict[str, Any]]:
        """Informations tarifaires de chaque PDL, indexées par numéro de PDL."""
        resultat: dict[str, dict[str, Any]] = {}
        infos_par_contrat: dict[str, dict[str, Any]] = {}

        for pdl_liste in await self._async_liste_pdl():
            numero = pdl_liste["numero"]
            pdc_contrat_id = pdl_liste["pdccontratId"]
            if pdc_contrat_id not in infos_par_contrat:
                infos_par_contrat[pdc_contrat_id] = await self._request(
                    "POST", API_INFOS_PDL, data={"pdc_contrat_id": pdc_contrat_id}
                )
            infos = infos_par_contrat[pdc_contrat_id]

            pdl = next(
                (p for p in infos.get("pdls") or [] if p.get("numero") == numero),
                pdl_liste,
            )
            adresses = {a["id"]: a for a in infos.get("adresses") or []}
            adresse = adresses.get(pdl.get("adresseId"))
            adresse_txt = format_adresse(adresse) if adresse else ""

            resultat[numero] = {
                "numero": numero,
                "pdc_contrat_id": pdc_contrat_id,
                "nom": f"{adresse_txt} - {numero}" if adresse_txt else numero,
                "type_compteur": pdl.get("typeCompteur"),
                "offre": pdl.get("offreCourante") or {},
            }
        return resultat
