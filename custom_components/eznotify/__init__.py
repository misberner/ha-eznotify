from __future__ import annotations

from homeassistant import core
from homeassistant.helpers import service
from homeassistant.components.notify.const import ATTR_MESSAGE, ATTR_TITLE, ATTR_DATA
from homeassistant.components.mobile_app import notify as mobile_app_notify
from homeassistant.components.mobile_app.const import DATA_NOTIFY as MOBILE_APP_DOMAIN

from homeassistant.helpers import event

from .const import DOMAIN
from .registry import Registry

async def notify_mobile_app(hass: core.HomeAssistant, call: core.ServiceCall):
    ref = service.async_extract_referenced_entity_ids(hass, call, expand_group=True)
    registry: Registry = hass.data[DOMAIN]

    targets = set()
    for entity_id in ref.referenced:
        if target := registry.target_for_entity_id(entity_id):
            targets.add(target)
    for entity_id in ref.indirectly_referenced:
        if target := registry.target_for_entity_id(entity_id):
            targets.add(target)
    for device_id in ref.referenced_devices:
        if target := registry.target_for_device_id(device_id):
            targets.add(target)
    
    if not targets:
        raise ValueError("no targets could be resolved")
    
    notify_svc = await mobile_app_notify.async_get_service(hass)

    message = call.data[ATTR_MESSAGE]
    kwargs = {}
    if title := call.data.get(ATTR_TITLE):
        kwargs[ATTR_TITLE] = title
    if data := call.data.get(ATTR_DATA):
        kwargs[ATTR_DATA] = data

    await notify_svc.async_send_message(message=message, target=targets, **kwargs)


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    async def bound_notify_mobile_app(call: core.ServiceCall):
        return await notify_mobile_app(hass, call)
    
    hass.data[DOMAIN] = Registry(hass)
    hass.services.async_register(DOMAIN, "notify_mobile_app", bound_notify_mobile_app)
    return True
