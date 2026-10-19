"""Target resolution and sending of eznotify."""

from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eznotify.const import DOMAIN

USERS = {}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def add_app(hass, entry_id, device_id, user_id, labels=(), seen=None):
    """A mobile_app registration with its device and device tracker."""
    entry = MockConfigEntry(
        domain="mobile_app",
        entry_id=entry_id,
        data={"device_id": device_id, "user_id": user_id, "device_name": entry_id},
    )
    entry.add_to_hass(hass)
    hass.data.setdefault("mobile_app", {}).setdefault("config_entries", {})[entry_id] = entry
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry_id, identifiers={("mobile_app", device_id)}, name=device_id
    )
    if labels:
        dr.async_get(hass).async_update_device(device.id, labels=set(labels))
    tracker = er.async_get(hass).async_get_or_create(
        "device_tracker", "mobile_app", device_id, device_id=device.id, config_entry=entry
    )
    if seen is not None:
        with patch("homeassistant.core.dt_util.utcnow", return_value=seen):
            hass.states.async_set(tracker.entity_id, "home")
    return device, tracker.entity_id


@pytest.fixture
async def home(hass):
    """Malte with one phone; Maren with a retired Pixel (registered first) and an iPhone."""
    import datetime as dt

    old = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    new = dt.datetime(2026, 10, 19, tzinfo=dt.UTC)
    for name in ("Malte", "Maren"):
        USERS[name] = (await hass.auth.async_create_user(name)).id
    assert await async_setup_component(hass, "person", {})
    await add_app(hass, "malte_iphone", "m1", USERS["Malte"], seen=new)
    await add_app(hass, "maren_pixel", "p1", USERS["Maren"], seen=old)
    _, maren_tracker = await add_app(hass, "maren_iphone", "i1", USERS["Maren"], seen=new)
    storage = hass.data["person"][1]
    await storage.async_create_item(
        {"name": "Malte", "user_id": USERS["Malte"], "device_trackers": []}
    )
    await storage.async_create_item(
        {
            "name": "Maren",
            "user_id": USERS["Maren"],
            "device_trackers": ["device_tracker.unifi_maren"],
        }
    )
    for entry_id in ("malte_iphone", "maren_pixel", "maren_iphone"):
        hass.services.async_register("notify", f"mobile_app_{entry_id}", record(entry_id))
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()
    return maren_tracker


SENT = []


def record(entry_id):
    async def handler(call):
        SENT.append((entry_id, dict(call.data)))

    return handler


async def send(hass, service="notify_mobile_app", **data):
    SENT.clear()
    await hass.services.async_call(DOMAIN, service, {"message": "hi", **data}, blocking=True)
    return {entry_id for entry_id, _ in SENT} or None


async def test_person_with_one_phone(hass, home):
    assert await send(hass, entity_id="person.malte") == {"malte_iphone"}


async def test_unlabelled_person_gets_the_phone_seen_last_not_the_first(hass, home):
    assert await send(hass, entity_id="person.maren") == {"maren_iphone"}


async def test_label_wins_and_applies_without_restart(hass, home):
    pixel = dr.async_get(hass).async_get_device({("mobile_app", "p1")})
    assert await send(hass, entity_id="person.maren") == {"maren_iphone"}
    dr.async_get(hass).async_update_device(pixel.id, labels={"notify_target"})
    with patch("custom_components.eznotify.registry.REFRESH_SECONDS", -1):
        assert await send(hass, entity_id="person.maren") == {"maren_pixel"}


async def test_device_tracker_of_a_person(hass, home):
    assert await send(hass, entity_id="device_tracker.unifi_maren") == {"maren_iphone"}


async def test_app_device_and_its_entities_reach_exactly_that_app(hass, home):
    pixel = dr.async_get(hass).async_get_device({("mobile_app", "p1")})
    assert await send(hass, device_id=pixel.id) == {"maren_pixel"}
    assert await send(hass, entity_id=home) == {"maren_iphone"}


async def test_user_id(hass, home):
    assert await send(hass, "notify_mobile_app_by_user_id", user_id=USERS["Maren"]) == {
        "maren_iphone"
    }


async def test_zone_means_whoever_is_in_it(hass, home):
    hass.states.async_set("zone.home", "2", {"persons": ["person.malte", "person.maren"]})
    assert await send(hass, entity_id="zone.home") == {"malte_iphone", "maren_iphone"}
    hass.states.async_set("zone.home", "1", {"persons": ["person.maren"]})
    assert await send(hass, entity_id="zone.home") == {"maren_iphone"}


async def test_empty_zone_sends_nothing_and_does_not_fail(hass, home):
    hass.states.async_set("zone.home", "0", {"persons": []})
    assert await send(hass, entity_id="zone.home") is None


async def test_unknown_target_fails(hass, home):
    with pytest.raises(ServiceValidationError):
        await send(hass, entity_id="person.nobody")


async def test_title_and_data_pass_through(hass, home):
    SENT.clear()
    await hass.services.async_call(
        DOMAIN,
        "notify_mobile_app",
        {"entity_id": "person.malte", "message": "m", "title": "t", "data": {"actions": []}},
        blocking=True,
    )
    assert SENT == [("malte_iphone", {"message": "m", "title": "t", "data": {"actions": []}})]
