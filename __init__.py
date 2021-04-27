"""Support for botvac connected Vorwerk vacuum cleaners."""
import asyncio
import logging

from pybotvac.exceptions import NeatoException
from pybotvac.robot import Robot
from pybotvac.vorwerk import Vorwerk
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import VorwerkState
from .const import (
    MIN_TIME_BETWEEN_UPDATES,
    VORWERK_DOMAIN,
    VORWERK_PLATFORMS,
    VORWERK_ROBOT_API,
    VORWERK_ROBOT_COORDINATOR,
    VORWERK_ROBOT_ENDPOINT,
    VORWERK_ROBOT_NAME,
    VORWERK_ROBOT_SECRET,
    VORWERK_ROBOT_SERIAL,
    VORWERK_ROBOT_TRAITS,
    VORWERK_ROBOTS,
)

_LOGGER = logging.getLogger(__name__)


VORWERK_SCHEMA = vol.Schema(
    vol.All(
        {
            vol.Required(VORWERK_ROBOT_NAME): cv.string,
            vol.Required(VORWERK_ROBOT_SERIAL): cv.string,
            vol.Required(VORWERK_ROBOT_SECRET): cv.string,
            vol.Optional(
                VORWERK_ROBOT_ENDPOINT, default="https://nucleo.ksecosys.com:4443"
            ): cv.string,
        }
    )
)

CONFIG_SCHEMA = vol.Schema(
    {VORWERK_DOMAIN: vol.Schema(vol.All(cv.ensure_list, [VORWERK_SCHEMA]))},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistantType, config: ConfigType) -> bool:
    """Set up the Vorwerk component."""
    hass.data[VORWERK_DOMAIN] = {}

    if VORWERK_DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                VORWERK_DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[VORWERK_DOMAIN],
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Set up config entry."""
    robots = await _async_create_robots(hass, entry.data[VORWERK_ROBOTS])

    robot_states = [VorwerkState(robot) for robot in robots]

    hass.data[VORWERK_DOMAIN][entry.entry_id] = {
        VORWERK_ROBOTS: [
            {
                VORWERK_ROBOT_API: r,
                VORWERK_ROBOT_COORDINATOR: _create_coordinator(hass, r),
            }
            for r in robot_states
        ]
    }

    for component in VORWERK_PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


def _create_coordinator(
    hass: HomeAssistantType, robot_state: VorwerkState
) -> DataUpdateCoordinator:
    async def async_update_data():
        """Fetch data from API endpoint."""
        await hass.async_add_executor_job(robot_state.update)

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=robot_state.robot.name,
        update_method=async_update_data,
        update_interval=MIN_TIME_BETWEEN_UPDATES,
    )


async def _async_create_robots(hass, robot_confs):
    def create_robot(config):
        return Robot(
            serial=config[VORWERK_ROBOT_SERIAL],
            secret=config[VORWERK_ROBOT_SECRET],
            traits=config.get(VORWERK_ROBOT_TRAITS, []),
            vendor=Vorwerk(),
            name=config[VORWERK_ROBOT_NAME],
            endpoint=config[VORWERK_ROBOT_ENDPOINT],
        )

    robots = []
    try:
        robots = await asyncio.gather(
            *(
                hass.async_add_executor_job(create_robot, robot_conf)
                for robot_conf in robot_confs
            ),
            return_exceptions=False,
        )
    except NeatoException as ex:
        _LOGGER.error("Failed to connect to robots: %s", ex)
        raise ConfigEntryNotReady from ex
    return robots


async def async_unload_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    unload_ok: bool = all(
        await asyncio.gather(
            *(
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in VORWERK_PLATFORMS
            )
        )
    )
    if unload_ok:
        hass.data[VORWERK_DOMAIN].pop(entry.entry_id)
    return unload_ok
