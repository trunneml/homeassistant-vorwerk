"""Support for Vorwerk sensors."""
from datetime import timedelta
import logging

from pybotvac.exceptions import NeatoRobotException

from homeassistant.components.sensor import DEVICE_CLASS_BATTERY
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.entity import Entity

from .const import SCAN_INTERVAL_MINUTES, VORWERK_DOMAIN, VORWERK_ROBOTS

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=SCAN_INTERVAL_MINUTES)

BATTERY = "Battery"


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Vorwerk sensor using config entry."""
    _LOGGER.debug("Adding sensors for vorwerk robots")
    async_add_entities(
        [
            VorwerkSensor(robot)
            for robot in hass.data[VORWERK_DOMAIN][entry.entry_id][VORWERK_ROBOTS]
        ],
        True,
    )


class VorwerkSensor(Entity):
    """Vorwerk sensor."""

    def __init__(self, robot):
        """Initialize Vorwerk sensor."""
        self.robot = robot
        self._available = False
        self._robot_name = f"{self.robot.name} {BATTERY}"
        self._robot_serial = self.robot.serial
        self._state = None

    def update(self):
        """Update Vorwerk Sensor."""
        try:
            self._state = self.robot.state
        except NeatoRobotException as ex:
            if self._available:
                _LOGGER.error(
                    "Vorwerk sensor connection error for '%s': %s", self.entity_id, ex
                )
            self._state = None
            self._available = False
            return

        self._available = True
        _LOGGER.debug("self._state=%s", self._state)

    @property
    def name(self):
        """Return the name of this sensor."""
        return self._robot_name

    @property
    def unique_id(self):
        """Return unique ID."""
        return self._robot_serial

    @property
    def device_class(self):
        """Return the device class."""
        return DEVICE_CLASS_BATTERY

    @property
    def available(self):
        """Return availability."""
        return self._available

    @property
    def state(self):
        """Return the state."""
        return self._state["details"]["charge"]

    @property
    def unit_of_measurement(self):
        """Return unit of measurement."""
        return PERCENTAGE

    @property
    def device_info(self):
        """Device info for robot."""
        return {"identifiers": {(VORWERK_DOMAIN, self._robot_serial)}}
