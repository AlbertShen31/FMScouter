"""Canonical directories under ``config/``.

Each domain keeps the same shape:

- ``active.json`` — last selected pack
- ``packs/`` — named JSON files
- optional ``default-overrides.json`` — edits to the built-in defaults

Role weight factory code lives in ``config/role_weights/fm26_role_weight_config.py``.
"""
from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent

ROLE_WEIGHTS_DIR = CONFIG_DIR / "role_weights"
ROLE_WEIGHTS_PACKS_DIR = ROLE_WEIGHTS_DIR / "packs"
ROLE_WEIGHTS_ACTIVE_PATH = ROLE_WEIGHTS_DIR / "active.json"
ROLE_WEIGHTS_DEFAULTS_PATH = ROLE_WEIGHTS_DIR / "default-overrides.json"

FORMATIONS_DIR = CONFIG_DIR / "formations"
FORMATIONS_PACKS_DIR = FORMATIONS_DIR / "packs"
FORMATIONS_ACTIVE_PATH = FORMATIONS_DIR / "active.json"

SETTINGS_DIR = CONFIG_DIR / "settings"
SETTINGS_PACKS_DIR = SETTINGS_DIR / "packs"
SETTINGS_ACTIVE_PATH = SETTINGS_DIR / "active.json"
SETTINGS_DEFAULTS_PATH = SETTINGS_DIR / "default-overrides.json"

# Pre-reorg locations (still read once, then moved into role_weights/).
LEGACY_ROLE_PACKS_DIR = CONFIG_DIR / "packs"
LEGACY_ROLE_ACTIVE_PATH = CONFIG_DIR / "active_pack.json"
LEGACY_ROLE_DEFAULTS_PATH = CONFIG_DIR / "default_overrides.json"
LEGACY_ROLE_OVERRIDES_PATH = CONFIG_DIR / "role_overrides.json"
