from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_WARN_DAYS, DEFAULT_WARN_DAYS


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def _extract_current_due_date(vehicle: dict[str, Any]) -> Optional[date]:
    # Prefer top-level due date when present
    due = _parse_date(vehicle.get("motTestDueDate"))
    if due:
        return due

    # Fallback: newest expiry date from motTests
    mot_tests = vehicle.get("motTests") or []
    best: Optional[date] = None
    for t in mot_tests:
        exp = _parse_date(t.get("expiryDate"))
        if exp and (best is None or exp > best):
            best = exp
    return best


def _extract_latest_test(vehicle: dict[str, Any]) -> Optional[dict[str, Any]]:
    mot_tests = vehicle.get("motTests") or []
    if not mot_tests:
        return None

    def key(t: dict[str, Any]) -> str:
        return str(t.get("completedDate") or t.get("completedDateTime") or "")

    return sorted(mot_tests, key=key, reverse=True)[0]


SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="due_date",
        name="MOT due date",
        device_class=SensorDeviceClass.DATE,
    ),
    SensorEntityDescription(
        key="days_remaining",
        name="MOT days remaining",
    ),
    SensorEntityDescription(
        key="status",
        name="MOT status",
    ),
    SensorEntityDescription(
        key="last_result",
        name="Last MOT result",
    ),
    SensorEntityDescription(
        key="last_test_date",
        name="Last MOT test date",
        device_class=SensorDeviceClass.DATE,
    ),
    SensorEntityDescription(
        key="make_model",
        name="Vehicle",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []

    for reg in coordinator.registrations:
        for desc in SENSORS:
            entities.append(DvsaMotSensor(entry, coordinator, reg, desc))

    async_add_entities(entities)


class DvsaMotSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, entry: ConfigEntry, coordinator, reg: str, desc: SensorEntityDescription) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._reg = reg
        self.entity_description = desc

        self._attr_unique_id = f"{entry.entry_id}_{reg}_{desc.key}"
        # Include reg in the entity name so multiple vehicles don’t collide
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
    def native_value(self):
        data = self.coordinator.data.get(self._reg) if self.coordinator.data else None
        if not isinstance(data, dict) or data.get("_error") == "not_found":
            return None

        due = _extract_current_due_date(data)
        latest = _extract_latest_test(data)

        warn_days = int(self._entry.options.get(CONF_WARN_DAYS, DEFAULT_WARN_DAYS))
        today = date.today()
        k = self.entity_description.key

        if k == "due_date":
            return due  # date object

        if k == "days_remaining":
            return (due - today).days if due else None

        if k == "status":
            if not due:
                return "unknown"
            if due < today:
                return "expired"
            if (due - today).days <= warn_days:
                return "expires_soon"
            return "valid"

        if k == "last_result":
            return latest.get("testResult") if latest else None

        if k == "last_test_date":
            if not latest:
                return None
            cd = latest.get("completedDate") or latest.get("completedDateTime")
            if isinstance(cd, str) and cd:
                for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S"):
                    try:
                        return datetime.strptime(cd[: len(fmt)], fmt).date()
                    except Exception:
                        continue
            return None

        if k == "make_model":
            mk = data.get("make")
            md = data.get("model")
            if mk and md:
                return f"{mk} {md}"
            return mk or md

        return None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self._reg) if self.coordinator.data else None
        if not isinstance(data, dict) or data.get("_error"):
            return {"error": data.get("_error")} if isinstance(data, dict) else None

        due = _extract_current_due_date(data)
        latest = _extract_latest_test(data)
        attrs = {
            "registration": data.get("registration") or self._reg,
            "make": data.get("make"),
            "model": data.get("model"),
            "fuelType": data.get("fuelType"),
            "primaryColour": data.get("primaryColour"),
            "registrationDate": data.get("registrationDate"),
            "manufactureDate": data.get("manufactureDate"),
            "mot_due_date": due.isoformat() if due else None,
            "hasOutstandingRecall": data.get("hasOutstandingRecall"),
        }
        if latest:
            attrs.update(
                {
                    "last_test_result": latest.get("testResult"),
                    "last_test_expiry": latest.get("expiryDate"),
                    "last_test_odometer": latest.get("odometerValue"),
                    "last_test_odometer_unit": latest.get("odometerUnit"),
                    "last_test_number": latest.get("motTestNumber"),
                }
            )
        return {k: v for k, v in attrs.items() if v is not None}
