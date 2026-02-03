from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="recall_status",
        name="Outstanding Recall",
        device_class=BinarySensorDeviceClass.SAFETY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[BinarySensorEntity] = []

    for reg in coordinator.registrations:
        for desc in BINARY_SENSORS:
            entities.append(DvsaMotBinarySensor(entry, coordinator, reg, desc))

    async_add_entities(entities)


class DvsaMotBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        reg: str,
        desc: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._reg = reg
        self.entity_description = desc

        self._attr_unique_id = f"{entry.entry_id}_{reg}_{desc.key}"
        self._attr_name = f"{reg} {desc.name}"
        self._attr_device_class = desc.device_class

    @property
    def available(self) -> bool:
        data = self.coordinator.data.get(self._reg) if self.coordinator.data else None
        if not isinstance(data, dict):
            return False
        return data.get("_error") != "api_error"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._reg)},
            "name": f"Vehicle {self._reg}",
            "manufacturer": "DVSA MOT history API",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        data = self.coordinator.data.get(self._reg) if self.coordinator.data else None
        if not isinstance(data, dict) or data.get("_error") == "not_found":
            return None

        if self.entity_description.key == "recall_status":
            # API returns boolean true/false or string "true"/"false" usually,
            # but let's be safe. 'hasOutstandingRecall' is the field.
            val = data.get("hasOutstandingRecall")
            if isinstance(val, str):
                return val.lower() == "true"
            return bool(val)

        return None
