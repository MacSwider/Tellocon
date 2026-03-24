"""
Bluetooth Low Energy handler for ESP32 + BMM150 magnetometer.

Connects to an ESP32 (e.g. XIAO ESP32-C6) over BLE and receives
magnetometer data used for heading computation.

Data formats accepted from the ESP32 firmware:
    Text "M:mx,my,mz"   -- calibrated magnetometer vector (preferred).
    Text "H:123" / "123" -- pre-computed heading 0-359 (fallback).
    Binary 2 bytes LE    -- heading as uint16 (legacy).

Signals emitted (PyQt5):
    mag_received(float, float, float)  -- raw (mx, my, mz) vector.
    heading_received(int)              -- pre-computed heading 0-359.
    connection_status(bool, str)       -- (connected?, human-readable message).

BLE service / characteristic UUIDs are defined in the ESP32 firmware
(tello_esp32_gy271_ble.ino) and mirrored here as class constants.

Usage example:
    handler = BluetoothHandler(device_name_pattern="XIAO")
    handler.mag_received.connect(my_callback)
    handler.start()           # runs its own asyncio event loop in a QThread
    ...
    handler.stop()            # graceful shutdown
"""

import asyncio
import logging
import re
import sys
import time

from bleak import BleakClient, BleakScanner
from PyQt5.QtCore import QThread, pyqtSignal

logging.getLogger('bleak').setLevel(logging.WARNING)

# Standard GATT characteristic short-UUIDs to skip during discovery
_STANDARD_GATT_UUIDS = frozenset((
    "2a00", "2a01", "2a04", "2a19",
    "2a24", "2a25", "2a26", "2a27", "2a28", "2a29", "2a2a",
))


class BluetoothHandler(QThread):
    """BLE client that receives magnetometer data from an ESP32.

    Runs an asyncio event loop in a dedicated thread.  Automatically
    scans, connects, and subscribes to notifications.  Reconnects on
    connection loss.
    """

    mag_received = pyqtSignal(float, float, float)
    heading_received = pyqtSignal(int)
    connection_status = pyqtSignal(bool, str)

    ESP32_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
    ESP32_CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

    def __init__(self, device_name_pattern="ESP32"):
        super().__init__()
        self.device_name_pattern = device_name_pattern
        self.client = None
        self.running = False
        self.connected = False
        self.loop = None

    # ----- Thread entry point -----

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main_loop())

    async def _main_loop(self):
        self.running = True
        while self.running:
            try:
                if not self.connected:
                    await self._connect()
                await asyncio.sleep(1)
            except Exception as e:
                logging.error(f"BLE loop error: {e}")
                if self.connected:
                    self.connected = False
                    self.connection_status.emit(False, f"Connection lost: {e}")
                await asyncio.sleep(2)

    # ----- Connection -----

    async def _connect(self):
        try:
            devices = await BleakScanner.discover(timeout=5.0)
            target = None
            for d in devices:
                if d.name and self.device_name_pattern.lower() in d.name.lower():
                    target = d
                    break
            if not target:
                self.connection_status.emit(
                    False, f"Device not found (pattern='{self.device_name_pattern}')")
                return

            self.client = BleakClient(target.address)
            await self.client.connect()

            if not self.client.is_connected:
                return

            self.connected = True
            self.connection_status.emit(True, f"Connected to {target.name}")

            char = self._find_characteristic()
            if char:
                if "notify" in char.properties:
                    await self.client.start_notify(char.uuid, self._on_data)
                else:
                    asyncio.create_task(self._poll(char.uuid))
            else:
                try:
                    await self.client.start_notify(
                        self.ESP32_CHARACTERISTIC_UUID, self._on_data)
                except Exception:
                    asyncio.create_task(self._poll(self.ESP32_CHARACTERISTIC_UUID))

        except Exception as e:
            logging.error(f"BLE connect error: {e}")
            self.connected = False
            self.connection_status.emit(False, f"Connection error: {e}")

    def _find_characteristic(self):
        """Look up the magnetometer characteristic in discovered services."""
        if not self.client:
            return None
        services = self.client.services

        for svc in services:
            for ch in svc.characteristics:
                if self._uuid_match(ch.uuid, self.ESP32_CHARACTERISTIC_UUID):
                    return ch

        for svc in services:
            for ch in svc.characteristics:
                short = ch.uuid[4:8].lower()
                if short in _STANDARD_GATT_UUIDS:
                    continue
                if "notify" in ch.properties or "read" in ch.properties:
                    return ch
        return None

    @staticmethod
    def _uuid_match(a, b):
        a = str(a).lower().replace("-", "")
        b = str(b).lower().replace("-", "")
        return a == b or a.endswith(b[-12:])

    # ----- Data handling -----

    def _on_data(self, _sender, data):
        """Parse incoming BLE notification."""
        if not data:
            return
        try:
            text = data.decode("utf-8").strip()
            mag = self._parse_mag(text)
            if mag is not None:
                self.mag_received.emit(*mag)
                return
            heading = self._parse_heading(text)
            if heading is not None:
                self.heading_received.emit(heading)
                return
        except UnicodeDecodeError:
            pass

        if len(data) >= 2:
            val = int.from_bytes(data[:2], byteorder="little")
            if 0 <= val <= 360:
                self.heading_received.emit(val % 360)

    async def _poll(self, uuid):
        """Fallback: poll the characteristic if notify is not available."""
        while self.running and self.connected:
            try:
                if self.client and self.client.is_connected:
                    data = await self.client.read_gatt_char(uuid)
                    self._on_data(uuid, data)
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.error(f"BLE poll error: {e}")
                await asyncio.sleep(1)

    # ----- Parsers -----

    _MAG_RE = re.compile(
        r"^\s*M:\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*$")

    def _parse_mag(self, text):
        """Parse 'M:mx,my,mz' vector. Returns (mx, my, mz) or None."""
        m = self._MAG_RE.match(text.strip())
        if m:
            try:
                return float(m.group(1)), float(m.group(2)), float(m.group(3))
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_heading(text):
        """Parse a heading integer from free-form text. Returns int or None."""
        for tok in re.findall(r"\d+\.?\d*", text):
            try:
                val = int(round(float(tok)))
                if val == 360:
                    val = 0
                if 0 <= val <= 359:
                    return val
            except ValueError:
                continue
        return None

    # ----- Shutdown -----

    def stop(self):
        self.running = False
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._disconnect(), self.loop)
            time.sleep(0.5)
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()

    async def _disconnect(self):
        try:
            if self.client and self.client.is_connected:
                await self.client.disconnect()
            self.connected = False
            self.connection_status.emit(False, "Disconnected")
        except Exception as e:
            logging.error(f"BLE disconnect error: {e}")
