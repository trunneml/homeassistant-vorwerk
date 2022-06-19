"""Support for Neato Connected Vacuums."""
from __future__ import annotations

import logging
from typing import Any

from pybotvac import Robot
from pybotvac.session import PasswordlessSession
from pybotvac.account import Account
from pybotvac.exceptions import NeatoRobotException
import voluptuous as vol

from homeassistant.components.vacuum import (
    ATTR_STATUS,
    STATE_CLEANING,
    STATE_DOCKED,
    STATE_IDLE,
    STATE_PAUSED,
    SUPPORT_BATTERY,
    SUPPORT_CLEAN_SPOT,
    SUPPORT_LOCATE,
    SUPPORT_PAUSE,
    SUPPORT_RETURN_HOME,
    SUPPORT_START,
    SUPPORT_STATE,
    SUPPORT_STOP,
    StateVacuumEntity,
)
from homeassistant.const import ATTR_MODE, CONF_TOKEN
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from . import VorwerkState
from .const import (
    ATTR_CATEGORY,
    ATTR_NAVIGATION,
    ATTR_ZONE,
    ATTR_MAP,
    VORWERK_DOMAIN,
    VORWERK_ROBOT_API,
    VORWERK_ROBOT_COORDINATOR,
    VORWERK_ROBOTS,
    VORWERK_CLIENT_ID,
)

_LOGGER = logging.getLogger(__name__)


SUPPORT_VORWERK = (
    SUPPORT_BATTERY
    | SUPPORT_PAUSE
    | SUPPORT_RETURN_HOME
    | SUPPORT_STOP
    | SUPPORT_START
    | SUPPORT_CLEAN_SPOT
    | SUPPORT_STATE
    | SUPPORT_LOCATE
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Vorwerk vacuum with config entry."""

    _LOGGER.debug("Adding vorwerk vacuums")
    async_add_entities(
        [
            VorwerkConnectedVacuum(
                robot[VORWERK_ROBOT_API], robot[VORWERK_ROBOT_COORDINATOR], robot[CONF_TOKEN]
            )
            for robot in hass.data[VORWERK_DOMAIN][entry.entry_id][VORWERK_ROBOTS]
        ],
        True,
    )

    platform = entity_platform.current_platform.get()
    assert platform is not None

    platform.async_register_entity_service(
        "custom_cleaning",
        {
            vol.Optional(ATTR_MODE, default=2): cv.positive_int,
            vol.Optional(ATTR_NAVIGATION, default=1): cv.positive_int,
            vol.Optional(ATTR_CATEGORY, default=4): cv.positive_int,
            vol.Optional(ATTR_ZONE): cv.string,
            vol.Optional(ATTR_MAP): cv.string,
        },
        "vorwerk_custom_cleaning",
    )


class VorwerkConnectedVacuum(CoordinatorEntity, StateVacuumEntity):
    """Representation of a Vorwerk Connected Vacuum."""

    def __init__(
        self, robot_state: VorwerkState, coordinator: DataUpdateCoordinator[Any], token
    ) -> None:
        """Initialize the Vorwerk Connected Vacuum."""
        super().__init__(coordinator)
        self.robot: Robot = robot_state.robot
        self._state: VorwerkState = robot_state

        self._name = f"{self.robot.name}"
        self._robot_serial = self.robot.serial
        self._token = token

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def supported_features(self) -> int:
        """Flag vacuum cleaner robot features that are supported."""
        return SUPPORT_VORWERK

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the vacuum cleaner."""
        return int(self._state.battery_level) if self._state.battery_level else None

    @property
    def available(self) -> bool:
        """Return if the robot is available."""
        return self._state.available

    @property
    def icon(self) -> str:
        """Return specific icon."""
        return "mdi:robot-vacuum-variant"

    @property
    def state(self) -> str | None:
        """Return the status of the vacuum cleaner."""
        return self._state.state if self._state else None

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._robot_serial

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the vacuum cleaner."""
        data: dict[str, Any] = {}

        if self._state.status is not None:
            data[ATTR_STATUS] = self._state.status

        return data

    @property
    def device_info(self) -> DeviceInfo:
        """Device info for robot."""
        return self._state.device_info

    def start(self) -> None:
        """Start cleaning or resume cleaning."""
        if not self._state:
            return
        try:
            if self._state.state == STATE_IDLE or self._state.state == STATE_DOCKED:
                self.robot.start_cleaning()
            elif self._state.state == STATE_PAUSED:
                self.robot.resume_cleaning()
        except NeatoRobotException as ex:
            _LOGGER.error(
                "Vorwerk vacuum connection error for '%s': %s", self.entity_id, ex
            )

    def pause(self) -> None:
        """Pause the vacuum."""
        try:
            self.robot.pause_cleaning()
        except NeatoRobotException as ex:
            _LOGGER.error(
                "Vorwerk vacuum connection error for '%s': %s", self.entity_id, ex
            )

    def return_to_base(self, **kwargs: Any) -> None:
        """Set the vacuum cleaner to return to the dock."""
        try:
            if self._state.state == STATE_CLEANING:
                self.robot.pause_cleaning()
            self.robot.send_to_base()
        except NeatoRobotException as ex:
            _LOGGER.error(
                "Vorwerk vacuum connection error for '%s': %s", self.entity_id, ex
            )

    def stop(self, **kwargs: Any) -> None:
        """Stop the vacuum cleaner."""
        try:
            self.robot.stop_cleaning()
        except NeatoRobotException as ex:
            _LOGGER.error(
                "Vorwerk vacuum connection error for '%s': %s", self.entity_id, ex
            )

    def locate(self, **kwargs: Any) -> None:
        """Locate the robot by making it emit a sound."""
        try:
            self.robot.locate()
        except NeatoRobotException as ex:
            _LOGGER.error(
                "Vorwerk vacuum connection error for '%s': %s", self.entity_id, ex
            )

    def clean_spot(self, **kwargs: Any) -> None:
        """Run a spot cleaning starting from the base."""
        try:
            self.robot.start_spot_cleaning()
        except NeatoRobotException as ex:
            _LOGGER.error(
                "Vorwerk vacuum connection error for '%s': %s", self.entity_id, ex
            )

    def vorwerk_custom_cleaning(
        self, mode: str, navigation: str, category: str, zone: str, map: str | None = None
    ) -> None:
        """Zone cleaning service call."""
        _LOGGER.debug("vorwerk_custom_cleaning called for %s / %s with token %s", map, zone, self._token)

        # create Vorwerk API session + account object and populate the robot list
        # (this necessary to update pybotvac internal states)
        session = PasswordlessSession(client_id=VORWERK_CLIENT_ID, token=self._token)
        account = Account(session)
        robots = account.robots

        _LOGGER.debug("  Robot list = %s", robots)

        map_id = None
        boundary_id = None

        if map is not None:
            # search map
            maps = account.persistent_maps[self._robot_serial]

            _LOGGER.debug("  Persistent map list = %s", maps)

            map_obj = None
            available_maps = []
            for m in maps:
                available_maps.append(m['name'])
                if map in m['name']:
                    map_obj = m

            if map_obj is None:
                _LOGGER.error("Map '%s' was not found for the robot '%s', list of valid maps: %s", map, self.entity_id, available_maps)
                return

            map_id = map_obj['id']
            _LOGGER.debug("  Found map %s = ID %s", map, map_id)

            if zone is not None:
                # search zone = boundary ID 
                boundaries = self.robot.get_map_boundaries(map_id).json()

                _LOGGER.debug("  Boundary list = %s", boundaries)

                boundary_obj = None
                available_zones = []
                for b in boundaries['data']['boundaries']:
                    available_zones.append(b['name'])
                    if zone in b['name']:
                        boundary_obj = b

                if boundary_obj is None:
                    _LOGGER.error("Zone '%s' was not found for the robot '%s' on map '%s', list of valid zones: %s", zone, self.entity_id, map, available_zones)
                    return

                boundary_id = boundary_obj['id']
                _LOGGER.debug("  Found baundary / zone %s = ID %s", zone, boundary_id)

        # start cleaning now
        _LOGGER.info("Start cleaning zone '%s' on map '%s' with robot %s", zone, map, self.entity_id)

        try:
            self.robot.start_cleaning(mode, navigation, category, boundary_id, map_id)
        except NeatoRobotException as ex:
            _LOGGER.error(
                "Vorwerk vacuum connection error for '%s': %s", self.entity_id, ex
            )
