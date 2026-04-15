from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path


HERMES_META_ROUTER = Path("/home/samade10/.hermes/hermes-agent/gateway/meta_router.py")


@lru_cache(maxsize=1)
def load_base_rules() -> tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]]]:
    """Load `_RULES` and `_MODE_RULES` directly from Hermes meta_router.py.

    The MR-ALS scripts are invoked with `/usr/bin/env python3` on this machine.
    Importing `gateway.meta_router` pulls in the full Hermes package tree, which
    requires extra dependencies such as PyYAML that are present in the Hermes
    venv but not necessarily in the system interpreter. Loading the module by
    file path keeps these scripts portable while still sharing the live rule
    definitions from Hermes.
    """
    spec = importlib.util.spec_from_file_location("hermes_meta_router_rules", HERMES_META_ROUTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Hermes meta-router rules from {HERMES_META_ROUTER}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    rules = getattr(module, "_RULES", None)
    mode_rules = getattr(module, "_MODE_RULES", None)
    if rules is None or mode_rules is None:
        raise RuntimeError(f"Hermes meta-router rules missing from {HERMES_META_ROUTER}")

    return rules, mode_rules
