from __future__ import annotations

from typing import Dict

import collections
import time

from homeassistant import core
from homeassistant.helpers import entity_registry, device_registry


class Registry:
    _target_by_device_id: Dict[str, str]
    _target_by_entity_id: Dict[str, str]
    _target_by_user_id: Dict[str, str]
    _last_refresh: float

    def __init__(self, hass: core.HomeAssistant):
        self._target_by_device_id = {}
        self._target_by_entity_id = {}
        self._target_by_user_id = {}
        self._last_refresh = 0

    def _maybe_refresh(self, hass: core.HomeAssistant):
        if time.time() - self._last_refresh > 30:
            self._refresh(hass)

    def _refresh(self, hass: core.HomeAssistant):
        self._target_by_device_id = {}
        self._target_by_entity_id = {}
        self._target_by_user_id = {}

        entries_by_user_id = collections.defaultdict(list)

        by_app_device_id = {}
        for id, entry in hass.data.get("mobile_app", {}).get("config_entries", {}).items():
            device_id = entry.data.get('device_id')
            if device_id:
                by_app_device_id[device_id] = id
            if user_id := entry.data.get('user_id'):
                entries_by_user_id[user_id].append((id, entry, device_id))

        dev_reg = device_registry.async_get(hass)
        for user_id, entries in entries_by_user_id.items():
            if len(entries) == 1:
                self._target_by_user_id[user_id] = entries[0][0]
            else:
                target_devices = [
                    (entry_id, dev_reg.async_get_device({('mobile_app', device_id)}))
                    for entry_id, _, device_id in entries
                    if entry_id and device_id
                ]
                target_devices = [
                    (entry_id, d) for (entry_id, d) in target_devices
                    if 'notify_target' in d.labels
                ]
                if target_devices:
                    self._target_by_user_id[user_id] = target_devices[0][0]
                else:
                    self._target_by_user_id[user_id] = entries[0][0]

        if by_app_device_id:
            ent_reg = entity_registry.async_get(hass)
            for app_device_id, target_id in by_app_device_id.items():
                dev_entry = dev_reg.async_get_device({('mobile_app', app_device_id)})
                if not dev_entry:
                    continue
                self._target_by_device_id[dev_entry.id] = target_id
                for entity in entity_registry.async_entries_for_device(ent_reg, dev_entry.id):
                    self._target_by_entity_id[entity.entity_id] = target_id

        self._last_refresh = time.time()

        if not self._target_by_user_id:
            return

        for person_id, person_data in hass.data["person"][1].data.items():
            if not (user_id := person_data.get("user_id")):
                continue
            if not (target_id := self._target_by_user_id.get(user_id)):
                continue
            self._target_by_entity_id[f"person.{person_id}"] = target_id
            for dev_tracker in person_data.get("device_trackers", []):
                self._target_by_entity_id[dev_tracker] = target_id

    def target_for_device_id(self, hass: core.HomeAssistant, device_id: str) -> str | None:
        target = self._target_by_device_id.get(device_id)
        if not target:
            self._maybe_refresh(hass)
            target = self._target_by_device_id.get(device_id)
        return target

    def target_for_entity_id(self, hass: core.HomeAssistant, entity_id: str) -> str | None:
        target = self._target_by_entity_id.get(entity_id)
        if not target:
            self._maybe_refresh(hass)
            target = self._target_by_entity_id.get(entity_id)
        return target

    def target_for_user_id(self, hass: core.HomeAssistant, user_id: str) -> str | None:
        target = self._target_by_user_id.get(user_id)
        if not target:
            self._maybe_refresh(hass)
            target = self._target_by_user_id.get(user_id)
        return target

