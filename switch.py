"""Support for Vorwerk Connected Vacuums switches."""
import logging

from pybotvac.exceptions import NeatoRobotException
from pybotvac.robot import Robot

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import VorwerkState
from .const import (
    VORWERK_DOMAIN,
    VORWERK_ROBOT_API,
    VORWERK_ROBOT_COORDINATOR,
    VORWERK_ROBOTS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Vorwerk switch with config entry."""
    _LOGGER.debug("Adding switches for vorwerk (%s)", entry.title)

    dev = [
        VorwerkScheduleSwitch(
            robot[VORWERK_ROBOT_API], robot[VORWERK_ROBOT_COORDINATOR]
        )
        for robot in hass.data[VORWERK_DOMAIN][entry.entry_id][VORWERK_ROBOTS]
    ]

    if not dev:
        return

    async_add_entities(dev, True)


class VorwerkScheduleSwitch(CoordinatorEntity, ToggleEntity):
    """Vorwerk Schedule Switches."""

    def __init__(
        self, robot_state: VorwerkState, coordinator: DataUpdateCoordinator
    ) -> None:
        """Initialize the Vorwerk Schedule switch."""
        super().__init__(coordinator)
        self.robot: Robot = robot_state.robot
        self._robot_name = f"{self.robot.name} Schedule"
        self._state: VorwerkState = robot_state
        self._robot_serial = self.robot.serial

    @property
    def name(self):
        """Return the name of the switch."""
        return self._robot_name

    @property
    def available(self):
        """Return True if entity is available."""
        return self._state.available

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._robot_serial

    @property
    def is_on(self):
        """Return true if switch is on."""
        if self._state.available:
            if self._state.schedule_enabled:
                return STATE_ON
            else:
                return STATE_OFF

    @property
    def device_info(self):
        """Device info for robot."""
        return self._state.device_info

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""

        def turn_on():
            try:
                self.robot.enable_schedule()
            except NeatoRobotException as ex:
                _LOGGER.error(
                    "Vorwerk switch connection error '%s': %s", self.entity_id, ex
                )

        await self.hass.async_add_executor_job(turn_on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""

        def turn_off():
            try:
                self.robot.disable_schedule()
            except NeatoRobotException as ex:
                _LOGGER.error(
                    "Vorwerk switch connection error '%s': %s", self.entity_id, ex
                )

        await self.hass.async_add_executor_job(turn_off)
        await self.coordinator.async_request_refresh()
