# Easy Mobile App Notify for Home Assistant

Push notifications to the companion app, addressed by who should get them
instead of by phone.

## Actions

`eznotify.notify_mobile_app`: `message`, optional `title` and `data` (passed
through to the app: actions, push options, ...). Targets:

- **person**: their phone (see below)
- **zone**: everyone currently in it, e.g. `zone.home` for whoever is home;
  an empty zone sends nothing and is not an error
- **device tracker** listed for a person: that person
- **mobile_app device** or one of its entities: exactly that app
- **area / label / group**: whatever of the above they contain

`eznotify.notify_mobile_app_by_user_id`: the same by HA user ID (`user_id`,
one or a list), e.g. from a trigger's context.

## Which phone

A person maps to the app registrations of their HA user. With several
registrations (old phone, tablet, watch), those whose device has the label
`notify_target` get the message; without any label, the one whose app
reported most recently. Label and registration changes apply within 30 s.

## Installation

Copy `custom_components/eznotify` to `/config/custom_components/`, add
`eznotify:` to `configuration.yaml`, restart.

## Tests

    uv venv && uv pip install pytest-homeassistant-custom-component
    .venv/bin/pytest
