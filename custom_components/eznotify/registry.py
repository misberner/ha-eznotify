from __future__ import annotations

from typing import Dict

from homeassistant import core
from homeassistant.helpers import entity_registry, device_registry


class Registry:
    _target_by_device_id: Dict[str, str]
    _target_by_entity_id: Dict[str, str]

    def __init__(self, hass: core.HomeAssistant):
        self._target_by_device_id = {}
        self._target_by_entity_id = {}

        by_app_device_id = {}
        by_user_id = {}
        for id, entry in hass.data.get("mobile_app", {}).get("config_entries", {}):
            if user_id := entry.data.get('user_id'):
                by_user_id[user_id] = id
            if device_id := entry.data.get('device_id'):
                by_app_device_id[device_id] = id

        if by_app_device_id:
            dev_reg = device_registry.async_get(hass)
            for app_device_id, target_id in by_app_device_id.keys():
                dev_entry = dev_reg.async_get_device({('mobile_app', app_device_id)})
                if not dev_entry:
                    continue
                self._target_by_device_id[dev_entry.id] = target_id
                for entity in entity_registry.async_entries_for_device(dev_reg, dev_entry.id):
                    self._target_by_entity_id[entity.entity_id] = target_id
        
        if not by_user_id:
            return
        
        for person_id, person_data in hass.data["person"][1].data:
            if not (user_id := person_data.get("user_id")):
                continue
            if not (target_id := by_user_id.get(user_id)):
                continue
            self._target_by_entity_id[f"person.{person_id}"] = target_id
            for dev_tracker in person_data.get("device_trackers", []):
                self._target_by_entity_id[dev_tracker] = target_id

    def target_for_device_id(self, device_id: str) -> str | None:
        return self._target_by_device_id.get(device_id)
    
    def target_for_entity_id(self, entity_id: str) -> str | None:
        return self._target_by_entity_id.get(entity_id)
