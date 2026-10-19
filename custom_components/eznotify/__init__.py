from __future__ import annotations

import logging

from homeassistant import core
from homeassistant.components.notify.const import ATTR_DATA, ATTR_MESSAGE, ATTR_TITLE
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import service
from homeassistant.util import slugify

from .const import DOMAIN
from .registry import Registry

_LOGGER = logging.getLogger(__name__)


def _expand_zones(hass: core.HomeAssistant, entity_ids) -> set[str]:
    """A zone stands for the persons currently in it, e.g. zone.home: whoever is home."""
    expanded = set()
    for entity_id in entity_ids:
        if entity_id.startswith("zone."):
            state = hass.states.get(entity_id)
            expanded.update((state.attributes.get("persons") or []) if state else [])
        else:
            expanded.add(entity_id)
    return expanded


def resolve_targets(hass: core.HomeAssistant, call: core.ServiceCall) -> set[str]:
    registry: Registry = hass.data[DOMAIN]
    targets = set()

    ref = service.async_extract_referenced_entity_ids(hass, call, expand_group=True)
    for entity_id in _expand_zones(hass, ref.referenced):
        if found := registry.targets_for_entity_id(hass, entity_id):
            targets |= found
        else:
            _LOGGER.warning("Could not resolve target for entity '%s'", entity_id)
    # Entities of a referenced area or device: only those that map to an app count.
    for entity_id in ref.indirectly_referenced:
        targets |= registry.targets_for_entity_id(hass, entity_id)
    for device_id in ref.referenced_devices:
        if found := registry.targets_for_device_id(hass, device_id):
            targets |= found
        else:
            _LOGGER.warning("Could not resolve target for device '%s'", device_id)

    user_ids = call.data.get("user_id") or []
    for user_id in [user_ids] if isinstance(user_ids, str) else user_ids:
        if found := registry.targets_for_user_id(hass, user_id):
            targets |= found
        else:
            _LOGGER.warning("Could not resolve target for user '%s'", user_id)
    return targets


async def notify_mobile_app(hass: core.HomeAssistant, call: core.ServiceCall):
    targets = resolve_targets(hass, call)
    if not targets:
        # A zone nobody is in is not an error: nobody to tell.
        entity_ids = call.data.get("entity_id") or []
        entity_ids = [entity_ids] if isinstance(entity_ids, str) else entity_ids
        if any(e.startswith("zone.") for e in entity_ids):
            _LOGGER.debug("No persons in the targeted zones, nothing sent")
            return
        raise ServiceValidationError("no targets could be resolved")

    payload = {ATTR_MESSAGE: call.data[ATTR_MESSAGE]}
    if title := call.data.get(ATTR_TITLE):
        payload[ATTR_TITLE] = title
    if data := call.data.get(ATTR_DATA):
        payload[ATTR_DATA] = data

    # Each app registration has its own legacy notify action, which (unlike
    # notify.send_message) passes data such as actions through to the app.
    entries = hass.data.get("mobile_app", {}).get("config_entries", {})
    for target in sorted(targets):
        if not (entry := entries.get(target)):
            continue
        name = slugify(f"mobile_app_{entry.data['device_name']}")
        if not hass.services.has_service("notify", name):
            _LOGGER.warning("No notify action notify.%s for app registration %s", name, target)
            continue
        await hass.services.async_call("notify", name, payload, blocking=True)


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    async def bound_notify_mobile_app(call: core.ServiceCall):
        return await notify_mobile_app(hass, call)

    hass.data[DOMAIN] = Registry(hass)
    hass.services.async_register(DOMAIN, "notify_mobile_app", bound_notify_mobile_app)
    hass.services.async_register(DOMAIN, "notify_mobile_app_by_user_id", bound_notify_mobile_app)
    return True
