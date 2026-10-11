"""Charge les modules sans dépendance HA (pricing, api, const) sans exécuter __init__.py."""

import sys
import types
from pathlib import Path

_PACKAGE_DIR = Path(__file__).parent.parent / "custom_components" / "labellenergie"

if "labellenergie" not in sys.modules:
    package = types.ModuleType("labellenergie")
    package.__path__ = [str(_PACKAGE_DIR)]
    sys.modules["labellenergie"] = package
