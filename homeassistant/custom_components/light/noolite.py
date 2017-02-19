import logging
import pickle
import sysv_ipc

import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.components.light import ATTR_BRIGHTNESS, Light, PLATFORM_SCHEMA
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
import homeassistant.helpers.config_validation as cv

from ..noolite import NooliteDevice


# Home Assistant depends on 3rd party packages for API specific code.
REQUIREMENTS = []
DEPENDENCIES = ['noolite']

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    # vol.Required(CONF_HOST): cv.string,
    # vol.Optional(CONF_USERNAME, default='admin'): cv.string,
    # vol.Optional(CONF_PASSWORD): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):

    """Find and return lights"""
    devices = config.get("lights", {})
    lights = []

    for object_id, device_config in devices.items():
        lights.append(
            NooliteLight(
                hass,
                object_id,
                device_config.get("friendly_name", object_id),
                device_config.get("tx_channel"),
                device_config.get("rx_channels", ()),
                device_config.get("dimmable", False),
            )
        )

    if not lights:
        _LOGGER.error("No switches added")
        return False

    add_devices(lights)


class NooliteLight(NooliteDevice, Light):
    """Representation of an Noolite Light."""

    def __init__(self, hass, object_id, name, tx_channel, rx_channels=(), dimmable=False):
        NooliteDevice.__init__(self, hass, object_id, name, tx_channel, rx_channels)

        self.entity_id = "light.{}".format(object_id)
        self._is_on = False
        self._dimmable = dimmable
        self._brightness = 0

    def process_rx_command(self, event_data):
        _LOGGER.info("Processing RX action %s on channel %s" % (event_data["action"], event_data["channel"]))
        if event_data["action"] == 'toggle':
            self._is_on = not self._is_on
        elif event_data["action"] == 'turn_on':
            self._is_on = True
        elif event_data["action"] == 'turn_off':
            self._is_on = False

        self.update_ha_state()

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def brightness(self):
        # Brightness of the light (an integer in the range 1-255).
        # Note that noolite lights have brightness in range 35-155
        return self._brightness

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._is_on

    def turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        _LOGGER.info('Turning on the noolite light at channel #{}'.format(self._tx_channel))

        if self._dimmable:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            self._hass.bus.async_fire("noolite.tx.send_command", ("brightness", self._tx_channel, (int(self._brightness / 255.0 * 150), )))
        else:
            self._hass.bus.async_fire("noolite.tx.send_command", ("turn_on", self._tx_channel, ()))

        self._is_on = True

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        _LOGGER.info('Turning off the noolite light at channel #{}'.format(self._tx_channel))
        self._hass.bus.fire("noolite.tx.send_command", ("turn_off", self._tx_channel, ()))
        self._is_on = False

    @property
    def supported_features(self):
        """Flag supported features."""
        return 1 if self._dimmable else 0

    def update(self):
        pass
