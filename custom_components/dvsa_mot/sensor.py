from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional, Tuple

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


_YMD_RE = re.compile(r"(?P<y>\d{4})[.\-/](?P<m>\d{2})[.\-/](?P<d>\d{2})")


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse common DVSA-ish datetime/date strings into a datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s:
        return None

    # Try ISO first (handles 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS', offsets, etc.)
    s_iso = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s_iso)
    except Exception:
        pass

    # Fallback: look for YYYY-MM-DD / YYYY.MM.DD / YYYY/MM/DD
    m = _YMD_RE.search(s)
    if not m:
        return None
    try:
        y = int(m.group("y"))
        mo = int(m.group("m"))
        d = int(m.group("d"))
        return datetime(y, mo, d)
    except Exception:
        return None


def _parse_date(value: Any) -> Optional[date]:
    dt = _parse_dt(value)
    return dt.date() if dt else None


def _sorted_tests(vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Return motTests sorted newest-first by completedDate (fallback expiryDate)."""
    mot_tests = vehicle.get("motTests") or []
    tests = [t for t in mot_tests if isinstance(t, dict)]

    def key(t: dict[str, Any]) -> datetime:
        cd = t.get("completedDate") or t.get("completedDateTime")
        dt = _parse_dt(cd)
        if dt:
            return dt
        exp = _parse_dt(t.get("expiryDate"))
        return exp or datetime.min

    return sorted(tests, key=key, reverse=True)


def _extract_latest_test(vehicle: dict[str, Any]) -> Optional[dict[str, Any]]:
    tests = _sorted_tests(vehicle)
    return tests[0] if tests else None


def _extract_current_due_date(vehicle: dict[str, Any]) -> Optional[date]:
    # Prefer top-level due date when present
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


def _latest_odometer(vehicle: dict[str, Any]) -> Tuple[Optional[float], Optional[str], Optional[date]]:
    """
    Returns (odometer_value, unit, as_of_date) from the latest MOT test entry.
    unit is typically 'mi' or 'km' when present.
    """
    latest = _extract_latest_test(vehicle)
    if not latest:
        return None, None, None

    odo = latest.get("odometerValue")
    unit = str(latest.get("odometerUnit") or "").lower().strip() or None
    as_of = _parse_date(latest.get("completedDate") or latest.get("completedDateTime"))

    try:
        odo_f = float(odo)
    except Exception:
        return None, unit, as_of

    return odo_f, unit, as_of


def _avg_annual_since_registration(vehicle: dict[str, Any]) -> Tuple[Optional[float], Optional[str], dict[str, Any]]:
    """
    Average annual mileage since registration:
      latest MOT odometer / (years since registration)

    Returns (avg_value, unit, debug_attrs)
    """
    reg_date = _parse_date(vehicle.get("registrationDate"))
    odo, unit, odo_as_of = _latest_odometer(vehicle)

    dbg: dict[str, Any] = {
        "registration_date": reg_date.isoformat() if reg_date else None,
        "odometer": odo,
        "odometer_unit": unit,
        "odometer_as_of": odo_as_of.isoformat() if odo_as_of else None,
    }

    if not reg_date or odo is None:
        return None, unit, dbg

    days = (date.today() - reg_date).days
    if days <= 0:
        return None, unit, dbg

    years = days / 365.25
    avg = odo / years
    return avg, unit, dbg


SENSORS: tuple[SensorEntityDescription, ...] = (
    # Core MOT
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

    # Metadata
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

    # History / computed
    SensorEntityDescription(
        key="mot_test_count",
        name="MOT test count",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="avg_annual_mileage_since_registration",
        name="Average annual mileage since registration",
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
            dt = _parse_date(latest.get("completedDate") or latest.get("completedDateTime"))
            return dt

        if k == "make_model":
            mk = data.get("make")
            md = data.get("model")
            if mk and md:
                return f"{mk} {md}"
            return mk or md

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

        if k == "mot_test_count":
            tests = data.get("motTests") or []
            return len(tests) if isinstance(tests, list) else None

        if k == "avg_annual_mileage_since_registration":
            avg, _unit, _dbg = _avg_annual_since_registration(data)
            return round(avg, 0) if avg is not None else None

        return None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self._reg) if self.coordinator.data else None
        if not isinstance(data, dict) or data.get("_error"):
            return {"error": data.get("_error")} if isinstance(data, dict) else None

        due = _extract_current_due_date(data)
        latest = _extract_latest_test(data)
        odo, odo_unit, odo_as_of = _latest_odometer(data)
        avg, avg_unit, avg_dbg = _avg_annual_since_registration(data)

        attrs: dict[str, Any] = {
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
            "latest_odometer": odo,
            "latest_odometer_unit": odo_unit,
            "latest_odometer_as_of": odo_as_of.isoformat() if odo_as_of else None,
        }

        if avg is not None:
            # Unit shown as an attribute to avoid dynamic HA unit complications
            if avg_unit:
                attrs["avg_annual_mileage_unit"] = f"{avg_unit}/yr"
            attrs["avg_annual_mileage_raw"] = avg_dbg

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
