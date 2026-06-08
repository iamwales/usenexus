"""
ConnectorRegistry — maps connector_id strings to connector instances.

Import order matters for circular-import safety — connectors import from
nexus_core, never from each other.
"""

from __future__ import annotations

from nexus_core.connectors.base import BaseConnector
from nexus_core.logging import get_logger

logger = get_logger(__name__)

# Lazy import map — connectors only loaded when first accessed
_CONNECTOR_MODULE_MAP: dict[str, str] = {
    "google_drive": "nexus_connectors.google_drive.connector.GoogleDriveConnector",
}

PLANNED_CONNECTORS: tuple[str, ...] = (
    "notion",
    "clickup",
    "slack",
    "google_calendar",
    "confluence",
    "github",
    "linear",
)

_instances: dict[str, BaseConnector] = {}


def get_connector(connector_id: str) -> BaseConnector:
    """
    Return a singleton connector instance for the given connector_id.
    Connectors are stateless — one instance shared across all tenants.
    """
    if connector_id in _instances:
        return _instances[connector_id]

    if connector_id not in _CONNECTOR_MODULE_MAP:
        raise ValueError(
            f"Unknown connector: {connector_id!r}. Available: {list(_CONNECTOR_MODULE_MAP.keys())}"
        )

    module_path = _CONNECTOR_MODULE_MAP[connector_id]
    module_name, class_name = module_path.rsplit(".", 1)

    import importlib

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    instance: BaseConnector = cls()

    _instances[connector_id] = instance
    logger.info("connector.loaded", connector_id=connector_id)
    return instance


def list_connectors() -> list[str]:
    return list(_CONNECTOR_MODULE_MAP.keys())


def is_supported(connector_id: str) -> bool:
    return connector_id in _CONNECTOR_MODULE_MAP
