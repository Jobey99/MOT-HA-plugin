from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_WARN_DAYS, DEFAULT_WARN_DAYS


def _parse_date(value: Any) -> Optional[date]:
    """Parse YYYY-MM-DD into a date."""
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


def _parse_completed_dt(value: Any) -> Optional[datetime]:
    """Parse completedDate strings like '2015-03-11 11:41:11'."""
    if not value or not isinstance(value, str):
        return None

    v = value.strip()
    fmts = (
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )
    for fmt in fmts:
        try:
            return datetime.strptime(v[: len(fmt)], fmt)
        except Exception:
            continue
    return None


def _sorted_tests(vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Return motTests sorted newest-first by completedDate."""
    mot_tests = vehicle.get("motTests") or []
    tests: list[dict[str, Any]] = [t for t in mot_tests if isinstance(t, dict)]

    def key(t: dict[str, Any]) -> datetime:
        dt = _parse_completed_dt(t.get("completedDate") or t.get("completedDateTime"))
        return dt or datetime.min

    return sorted(tests, key=key, reverse=True)


def _extract_current_due_date(vehicle: dict[str, Any]) -> Optional[date]:
    # Prefer top-level due date if present
    due = _parse_date(vehicle.get("motTestDueDate"))
    if due:
        return due

    # Fallback: newest expiryDate from motTests
    best: Optional[date] = None
    for t in _sorted_tests(vehicle):
        exp = _parse_date(t.get("expiryDate"))
        if exp and (best is None or exp > best):
            best = exp
    return best


def _extract_latest_test(vehicle: dict[str, Any]) -> Optional[dict[str, Any]]:
    tests = _sorted_tests(vehicle)
    return tests[0] if tests else None


def _annual_mileage_estimate(vehicle: dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    """
    Estimate annual mileage from last two MOT tests with usable odometer readings.

    Returns (estimate_value, unit) where unit is 'mi' or 'km' (from odometerUnit).
    """
    tests = _sorted_tests(vehicle)

    usable: list[tuple[datetime, float, str]] = []
    for t in tests:
        dt = _parse_completed_dt(t.get("completedDate") or t.get("completedDateTime"))
        if not dt:
            continue

        # Only use OK readings
        if str(t.get("odometerResultType") or "").upper() != "OK":
            continue

        odo = t.get("odometerValue")
        unit = str(t.get("odometerUnit") or "").lower().strip()
        if unit not in ("mi", "km"):
            continue
        try:
            odo_f = float(odo)
        except Exception:
            continue

        usable.append((dt, odo_f, unit))
        if len(usable) >= 2:
            break

    if len(usable) < 2:
        return None, None

    (d1, o1, u1), (d2, o2, u2) = usable[0], usable[1]

    # If units differ between tests, skip (rare, but possible)
    if u1 != u2:
        return None, None

    days = (d1 - d2).days
    if days <= 0:
        return None, None

    delta = o1 - o2
    if delta <= 0:
        # no increase or decrease: could be clocking, odometer reset, or data issues
        return None, u1

    estimate = (delta / days) * 365.25
    return estimate, u1


SENSORS: tuple[SensorEntityDescription, ...] = (
    # Existing
    SensorEntityDescription(
        key="due_date",
        name="MOT due date",
        device_class=SensorDeviceClass.DATE,
    ),
    SensorEntityDescription(
        key="days_remaining",
        name="MOT days remaining",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
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

    # New: metadata
    SensorEntityDescription(
        key="engine_size",
        name="Engine size",
        native_unit_of_measurement="cc",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="fuel_type",
        name="Fuel type",
    ),
    SensorEntityDescription(
        key="primary_colour",
        name="Primary colour",
    ),
    SensorEntityDescription(
        key="secondary_colour",
        name="Secondary colour",
    ),
    SensorEntityDescription(
        key="registration_date",
        name="Registration date",
        device_class=SensorDeviceClass.DATE,
    ),
    SensorEntityDescription(
        key="manufacture_date",
        name="Manufacture date",
        device_class=SensorDeviceClass.DATE,
    ),

    # New: estimated annual mileage (unit is dynamic; we’ll expose unit in attributes too)
    SensorEntityDescription(
        key="annual_mileage_estimate",
        name="Estimated annual mileage",
        state_class=SensorStateClass.MEASUREMENT,
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
        self._attr_name = f"{reg} {desc.name}"
        self._attr_device_class = desc.device_class
        self._attr_native_unit_of_measurement = desc.native_unit_of_measurement

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
            return due

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
            dt = _parse_completed_dt(latest.get("completedDate") or latest.get("completedDateTime"))
            return dt.date() if dt else None

        if k == "make_model":
            mk = data.get("make")
            md = data.get("model")
            if mk and md:
                return f"{mk} {md}"
            return mk or md

        # Metadata sensors
        if k == "engine_size":
            v = data.get("engineSize")
            try:
                return int(v) if v is not None else None
            except Exception:
                return None

        if k == "fuel_type":
            return data.get("fuelType")

        if k == "primary_colour":
            return data.get("primaryColour")

        if k == "secondary_colour":
            return data.get("secondaryColour")

        if k == "registration_date":
            return _parse_date(data.get("registrationDate"))

        if k == "manufacture_date":
            return _parse_date(data.get("manufactureDate"))

        # Annual mileage estimate
        if k == "annual_mileage_estimate":
            est, _unit = _annual_mileage_estimate(data)
            if est is None:
                return None
            return round(est, 0)

        return None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self._reg) if self.coordinator.data else None
        if not isinstance(data, dict) or data.get("_error"):
            return {"error": data.get("_error")} if isinstance(data, dict) else None

        due = _extract_current_due_date(data)
        latest = _extract_latest_test(data)
        est, est_unit = _annual_mileage_estimate(data)

        attrs = {
            "registration": data.get("registration") or self._reg,
            "make": data.get("make"),
            "model": data.get("model"),
            "fuelType": data.get("fuelType"),
            "primaryColour": data.get("primaryColour"),
            "secondaryColour": data.get("secondaryColour"),
            "engineSize": data.get("engineSize"),
            "registrationDate": data.get("registrationDate"),
            "manufactureDate": data.get("manufactureDate"),
            "mot_due_date": due.isoformat() if due else None,
            "hasOutstandingRecall": data.get("hasOutstandingRecall"),
            "annual_mileage_estimate_unit": (f"{est_unit}/yr" if est_unit else None),
        }

        if est is not None and est_unit is not None:
            attrs["annual_mileage_estimate_raw"] = est

        if latest:
            attrs.update(
                {
                    "last_test_result": latest.get("testResult"),
                    "last_test_expiry": latest.get("expiryDate"),
                    "last_test_odometer": latest.get("odometerValue"),
                    "last_test_odometer_unit": latest.get("odometerUnit"),
                    "last_test_odometer_result_type": latest.get("odometerResultType"),
                    "last_test_number": latest.get("motTestNumber"),
                }
            )

        return {k: v for k, v in attrs.items() if v is not None}
