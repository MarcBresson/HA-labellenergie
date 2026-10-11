from datetime import UTC, datetime, timedelta

import pytest

from labellenergie.pricing import (
    TIMEZONE,
    is_heure_creuse,
    parse_plages_hc,
    plages_creuses,
    prix_actuel,
    prochain_changement,
)

PLAGES = ["1h04 - 7h04", "14h34 - 16h34"]
OFFRE_HPHC = {"base": None, "hp": 0.189, "hc": 0.14676, "plagesHc": PLAGES}
OFFRE_BASE = {"base": 0.2, "hp": None, "hc": None, "plagesHc": []}


def paris(h: int, m: int = 0, jour: int = 15) -> datetime:
    return datetime(2026, 10, jour, h, m, tzinfo=TIMEZONE)


def test_parse():
    assert parse_plages_hc(PLAGES) == [(64, 424), (874, 994)]
    assert parse_plages_hc(["22h - 6h", "n'importe quoi", "2h30-3h"]) == [
        (1320, 360),
        (150, 180),
    ]
    assert parse_plages_hc(None) == []


@pytest.mark.parametrize(
    ("h", "m", "attendu"),
    [
        (1, 3, False),
        (1, 4, True),  # début inclus
        (7, 3, True),
        (7, 4, False),  # fin exclue
        (12, 0, False),
        (14, 34, True),
        (16, 33, True),
        (16, 34, False),
    ],
)
def test_heure_creuse(h, m, attendu):
    assert is_heure_creuse(paris(h, m), parse_plages_hc(PLAGES)) is attendu


def test_plage_passant_minuit():
    plages = parse_plages_hc(["22h00 - 6h00"])
    assert is_heure_creuse(paris(23), plages)
    assert is_heure_creuse(paris(0), plages)
    assert is_heure_creuse(paris(5, 59), plages)
    assert not is_heure_creuse(paris(6), plages)
    assert not is_heure_creuse(paris(21, 59), plages)


def test_heure_locale_convertie_depuis_utc():
    # 23h30 UTC le 14 octobre = 1h30 à Paris (CEST) : heure creuse
    instant = datetime(2026, 10, 14, 23, 30, tzinfo=UTC)
    assert is_heure_creuse(instant, parse_plages_hc(PLAGES))


def test_prix_actuel_hphc():
    assert prix_actuel(OFFRE_HPHC, paris(3)).prix == 0.14676
    assert prix_actuel(OFFRE_HPHC, paris(3)).heure_creuse is True
    assert prix_actuel(OFFRE_HPHC, paris(12)).prix == 0.189
    assert prix_actuel(OFFRE_HPHC, paris(12)).option == "hp_hc"


def test_prix_actuel_base():
    courant = prix_actuel(OFFRE_BASE, paris(3))
    assert (courant.prix, courant.heure_creuse, courant.option) == (0.2, None, "base")


def test_prochain_changement_dans_la_journee():
    plages = parse_plages_hc(PLAGES)
    assert prochain_changement(plages, paris(0, 30)) == paris(1, 4)
    assert prochain_changement(plages, paris(1, 4)) == paris(7, 4)  # strictement après
    assert prochain_changement(plages, paris(8)) == paris(14, 34)
    assert prochain_changement(plages, paris(8, 0).replace(second=30)) == paris(14, 34)


def test_prochain_changement_apres_derniere_plage_donne_le_lendemain():
    plages = parse_plages_hc(PLAGES)
    assert prochain_changement(plages, paris(17)) == paris(1, 4, jour=16)


def test_prochain_changement_plages_jointives_ignore_la_jonction():
    plages = parse_plages_hc(["22h - 2h", "2h - 6h"])
    assert prochain_changement(plages, paris(23)) == paris(6, jour=16)
    assert prochain_changement(plages, paris(1)) == paris(6)
    assert prochain_changement(plages, paris(12)) == paris(22)


def test_prochain_changement_sans_bascule():
    assert prochain_changement([], paris(12)) is None
    assert prochain_changement(parse_plages_hc(["0h - 24h"]), paris(12)) is None


def test_prochain_changement_est_dans_le_futur():
    plages = parse_plages_hc(PLAGES)
    now = paris(7, 3)
    assert 0 < (prochain_changement(plages, now) - now).total_seconds() <= timedelta(days=1).total_seconds()


def test_plages_creuses_sur_une_journee():
    plages = parse_plages_hc(PLAGES)
    assert plages_creuses(plages, paris(0), paris(0, jour=16)) == [
        (paris(1, 4), paris(7, 4)),
        (paris(14, 34), paris(16, 34)),
    ]


def test_plages_creuses_chevauchement_et_minuit():
    plages = parse_plages_hc(["22h - 6h"])
    # À 3h : la période commencée la veille est incluse
    assert plages_creuses(plages, paris(3), paris(4)) == [(paris(22, jour=14), paris(6))]
    # Fenêtre d'un jour : deux périodes qui se touchent la fenêtre
    assert plages_creuses(plages, paris(8), paris(8, jour=16)) == [
        (paris(22), paris(6, jour=16)),
    ]


def test_plages_creuses_fusionne_les_plages_jointives():
    plages = parse_plages_hc(["22h - 2h", "2h - 6h"])
    assert plages_creuses(plages, paris(12), paris(12, jour=16)) == [
        (paris(22), paris(6, jour=16)),
    ]


def test_plages_creuses_vide():
    assert plages_creuses([], paris(0), paris(0, jour=20)) == []
