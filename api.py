"""Auth sessions for pybotvac."""
from __future__ import annotations

from functools import wraps
import logging

import pybotvac
from pybotvac.exceptions import NeatoRobotException

from homeassistant.components.vacuum import (
    STATE_CLEANING,
    STATE_DOCKED,
    STATE_ERROR,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_RETURNING,
)

from .const import (
    ACTION,
    ALERTS,
    ERRORS,
    MODE,
    ROBOT_ACTION_DOCKING,
    ROBOT_STATE_BUSY,
    ROBOT_STATE_ERROR,
    ROBOT_STATE_IDLE,
    ROBOT_STATE_PAUSE,
    VORWERK_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class VorwerkSession(pybotvac.PasswordlessSession):
    """PasswordlessSession pybotvac session for Vorwerk cloud."""

    # The client_id is the same for all users.
    CLIENT_ID = "KY4YbVAvtgB7lp8vIbWQ7zLk3hssZlhR"

    def __init__(self):
        """Initialize Vorwerk cloud session."""
        super().__init__(client_id=VorwerkSession.CLIENT_ID, vendor=pybotvac.Vorwerk())

    @property
    def token(self):
        """Return the token dict. Contains id_token, access_token and refresh_token."""
        return self._token


def when_available(func):
    """Prevent calling the method and return None when not available."""

    @wraps(func)
    def wrapper(self, *args, **kw):
        if not self.available:
            return None
        return func(self, *args, **kw)

    return wrapper


class VorwerkState:
    """Class to convert robot_state dict to more useful object."""

    def __init__(self, robot: pybotvac.Robot) -> None:
        """Initialize new vorwerk vacuum state."""
        self.robot = robot
        self.robot_state = {}
        self.robot_info = {}

    @property
    def available(self) -> bool:
        """Return true when robot state is available."""
        return bool(self.robot_state)

    def update(self):
        """Update robot state and robot info."""
        _LOGGER.debug("Running Vorwerk Vacuums update for '%s'", self.robot.name)
        self._update_robot_info()
        self._update_state()

    def _update_state(self):
        try:
            if self.robot_info is None:
                self.robot_info = self.robot.get_general_info().json().get("data")
        except NeatoRobotException:
            _LOGGER.warning("Couldn't fetch robot information of %s", self.robot.name)

    def _update_robot_info(self):
        try:
            self.robot_state = self.robot.state
        except NeatoRobotException as ex:
            if self.available:  # print only once when available
                _LOGGER.error(
                    "Vorwerk vacuum connection error for '%s': %s", self.robot.name, ex
                )
            self.robot_state = {}
            return

    @property
    @when_available
    def docked(self):
        """Vacuum is docked."""
        return (
            self.robot_state["state"] == ROBOT_STATE_IDLE
            and self.robot_state["details"]["isDocked"]
        )

    @property
    @when_available
    def charging(self):
        """Vacuum is charging."""
        return (
            self.robot_state.get("state") == ROBOT_STATE_IDLE
            and self.robot_state["details"]["isCharging"]
        )

    @property
    @when_available
    def state(self) -> str | None:
        """Return Home Assistant vacuum state."""
        robot_state = self.robot_state.get("state")
        state = None
        if self.charging or self.docked:
            state = STATE_DOCKED
        elif robot_state == ROBOT_STATE_IDLE:
            state = STATE_IDLE
        elif robot_state == ROBOT_STATE_BUSY:
            if robot_state["action"] != ROBOT_ACTION_DOCKING:
                state = STATE_RETURNING
            else:
                state = STATE_CLEANING
        elif robot_state == ROBOT_STATE_PAUSE:
            state = STATE_PAUSED
        elif robot_state == ROBOT_STATE_ERROR:
            state = STATE_ERROR
        return state

    @property
    @when_available
    def alert(self) -> str | None:
        """Return vacuum alert message."""
        if "alert" in self.robot_state:
            return ALERTS.get(self.robot_state["alert"], self.robot_state["alert"])
        return None

    @property
    @when_available
    def status(self) -> str | None:
        """Return vacuum status message."""
        status = None

        if self.state == STATE_ERROR:
            status = self._error_status()
        elif self.alert:
            status = self.alert
        elif self.state == STATE_DOCKED:
            if self.charging:
                status = "Charging"
            if self.docked:
                status = "Docked"
        elif self.state == STATE_IDLE:
            status = "Stopped"
        elif self.state == STATE_CLEANING:
            status = self._cleaning_status()
        elif self.state == STATE_PAUSED:
            status = "Paused"

        return status

    def _error_status(self):
        """Return error status."""
        robot_state = self.robot_state.get("state")
        return ERRORS.get(robot_state["error"], robot_state["error"])

    def _cleaning_status(self):
        """Return cleaning status."""
        robot_state = self.robot_state.get("state")
        status_items = [
            MODE.get(robot_state["cleaning"]["mode"]),
            ACTION.get(robot_state["action"]),
        ]
        if (
            "boundary" in robot_state["cleaning"]
            and "name" in robot_state["cleaning"]["boundary"]
        ):
            status_items.append(robot_state["cleaning"]["boundary"]["name"])
        return " ".join(s for s in status_items if s)

    @property
    @when_available
    def battery_level(self):
        """Return the battery level of the vacuum cleaner."""
        return self.robot_state["details"]["charge"]

    @property
    def device_info(self):
        """Device info for robot."""
        info = {
            "identifiers": {(VORWERK_DOMAIN, self.robot.serial)},
            "name": self.robot.name,
        }
        if self.robot_info:
            info["manufacturer"] = self.robot_info["battery"]["vendor"]
            info["model"] = self.robot_info["model"]
            info["sw_version"] = self.robot_info["firmware"]
        return info

    @property
    @when_available
    def schedule_enabled(self):
        """Return True when schedule is enabled."""
        return bool(self.robot_state["details"]["isScheduleEnabled"])
