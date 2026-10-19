from __future__ import annotations

import collections
import time
from typing import Dict, FrozenSet

from homeassistant import core
from homeassistant.helpers import device_registry, entity_registry

NOTIFY_TARGET_LABEL = "notify_target"
REFRESH_SECONDS = 30


class Registry:
    """Maps entities, devices and users to mobile_app config entries (notify targets).

    A person (and each of their device trackers) maps to the app registrations
    of their user.  With several registrations, those whose device carries the
    notify_target label are used; without any label, the one whose app reported
    most recently, so a retired phone does not keep receiving notifications.
    """

    _targets_by_device_id: Dict[str, FrozenSet[str]]
    _targets_by_entity_id: Dict[str, FrozenSet[str]]
    _targets_by_user_id: Dict[str, FrozenSet[str]]
    _last_refresh: float

    def __init__(self, hass: core.HomeAssistant):
        self._targets_by_device_id = {}
        self._targets_by_entity_id = {}
        self._targets_by_user_id = {}
        self._last_refresh = 0

    def _maybe_refresh(self, hass: core.HomeAssistant):
        # Also when a lookup hits, so new labels and registrations apply without a restart.
        if time.time() - self._last_refresh > REFRESH_SECONDS:
            self._refresh(hass)

    @staticmethod
    def _last_seen(hass: core.HomeAssistant, ent_reg, device) -> float:
        """When the app on this device last reported anything, as a timestamp."""
        latest = 0.0
        for entity in entity_registry.async_entries_for_device(ent_reg, device.id):
            if (state := hass.states.get(entity.entity_id)) is not None:
                latest = max(latest, state.last_reported.timestamp())
        return latest

    def _user_targets(self, hass, dev_reg, ent_reg, entries) -> FrozenSet[str]:
        if len(entries) == 1:
            return frozenset([entries[0][0]])
        devices = [
            (entry_id, dev_reg.async_get_device({("mobile_app", device_id)}))
            for entry_id, device_id in entries
            if device_id
        ]
        devices = [(entry_id, d) for entry_id, d in devices if d is not None]
        labelled = [entry_id for entry_id, d in devices if NOTIFY_TARGET_LABEL in d.labels]
        if labelled:
            return frozenset(labelled)
        if devices:
            return frozenset([max(devices, key=lambda t: self._last_seen(hass, ent_reg, t[1]))[0]])
        return frozenset([entries[0][0]])

    def _refresh(self, hass: core.HomeAssistant):
        dev_reg = device_registry.async_get(hass)
        ent_reg = entity_registry.async_get(hass)
        by_device_id = {}
        by_entity_id = {}
        by_user_id = {}

        entries_by_user_id = collections.defaultdict(list)
        by_app_device_id = {}
        for entry_id, entry in hass.data.get("mobile_app", {}).get("config_entries", {}).items():
            device_id = entry.data.get("device_id")
            if device_id:
                by_app_device_id[device_id] = entry_id
            if user_id := entry.data.get("user_id"):
                entries_by_user_id[user_id].append((entry_id, device_id))

        for user_id, entries in entries_by_user_id.items():
            by_user_id[user_id] = self._user_targets(hass, dev_reg, ent_reg, entries)

        # An app device and its own entities always reach exactly that app.
        for app_device_id, entry_id in by_app_device_id.items():
            dev_entry = dev_reg.async_get_device({("mobile_app", app_device_id)})
            if not dev_entry:
                continue
            by_device_id[dev_entry.id] = frozenset([entry_id])
            for entity in entity_registry.async_entries_for_device(ent_reg, dev_entry.id):
                by_entity_id[entity.entity_id] = frozenset([entry_id])

        person_data = hass.data.get("person")
        for person_id, data in person_data[1].data.items() if person_data else []:
            if not (targets := by_user_id.get(data.get("user_id"))):
                continue
            by_entity_id[f"person.{person_id}"] = targets
            for dev_tracker in data.get("device_trackers", []):
                by_entity_id.setdefault(dev_tracker, targets)

        self._targets_by_device_id = by_device_id
        self._targets_by_entity_id = by_entity_id
        self._targets_by_user_id = by_user_id
        self._last_refresh = time.time()

    def targets_for_device_id(self, hass: core.HomeAssistant, device_id: str) -> FrozenSet[str]:
        self._maybe_refresh(hass)
        return self._targets_by_device_id.get(device_id, frozenset())

    def targets_for_entity_id(self, hass: core.HomeAssistant, entity_id: str) -> FrozenSet[str]:
        self._maybe_refresh(hass)
        return self._targets_by_entity_id.get(entity_id, frozenset())

    def targets_for_user_id(self, hass: core.HomeAssistant, user_id: str) -> FrozenSet[str]:
        self._maybe_refresh(hass)
        return self._targets_by_user_id.get(user_id, frozenset())
