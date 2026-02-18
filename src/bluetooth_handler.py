import asyncio
import logging
import sys
from bleak import BleakClient, BleakScanner
from PyQt5.QtCore import QThread, pyqtSignal
import re

logging.getLogger('bleak').setLevel(logging.WARNING)

"""
Bluetooth Handler for ESP32 with GY-271 magnetometer

Expected ESP32 data format (one of):
- Text: "heading: 123" or "123" or "H:123" (heading 0-359)
- Binary: 16-bit integer (little-endian) representing heading 0-359

The handler will automatically:
1. Scan for ESP32 devices
2. Connect to the first matching device
3. Read/notify on characteristic data
4. Parse heading values and emit signals
"""


class BluetoothHandler(QThread):
    """Handler for Bluetooth communication with ESP32"""
    heading_received = pyqtSignal(int)  # Emits heading value (0-359)
    connection_status = pyqtSignal(bool, str)  # Emits (connected, message)
    
    # UUID z firmware ESP32 (tello_esp32_gy271_ble.ino)
    ESP32_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
    ESP32_CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
    
    def __init__(self, device_name_pattern="ESP32"):
        super().__init__()
        self.device_name_pattern = device_name_pattern
        self.client = None
        self.running = False
        self.connected = False
        self.loop = None
        
    def run(self):
        """Run the async event loop"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._run_async())
        
    async def _run_async(self):
        """Main async loop"""
        self.running = True
        while self.running:
            try:
                if not self.connected:
                    await self._connect()
                await asyncio.sleep(1)
            except Exception as e:
                logging.error(f"Bluetooth error: {e}")
                if self.connected:
                    self.connected = False
                    self.connection_status.emit(False, f"Connection lost: {str(e)}")
                await asyncio.sleep(2)
    
    async def _connect(self):
        """Connect to ESP32 via Bluetooth"""
        try:
            # Scan for devices
            devices = await BleakScanner.discover(timeout=5.0)
            
            target_device = None
            for device in devices:
                # device.name can be None, so we need to check it
                if device.name and self.device_name_pattern.lower() in device.name.lower():
                    target_device = device
                    break
            
            if not target_device:
                self.connection_status.emit(False, f"ESP32 device not found (looking for '{self.device_name_pattern}')")
                return
            
            # Connect to device
            self.client = BleakClient(target_device.address)
            await self.client.connect()
            
            if self.client.is_connected:
                self.connected = True
                self.connection_status.emit(True, f"Connected to {target_device.name}")
                
                # Try to find the characteristic (Bleak discovers services on connect)
                services = self.client.services
                characteristic = None
                # Standard GATT UUIDs do odfiltrowania (np. nazwa "nimble" = 0x2a00)
                skip_uuids = ("2a00", "2a01", "2a04", "2a19", "2a24", "2a25", "2a26", "2a27", "2a28", "2a29", "2a2a")

                def uuid_match(uuid_str, ref):
                    if not uuid_str or not ref:
                        return False
                    s = str(uuid_str).lower().replace("-", "")
                    r = str(ref).lower().replace("-", "")
                    return s == r or s.endswith(r[-12:])

                # 1) Szukaj charakterystyki z azymutem (UUID z ESP32 .ino)
                for service in services:
                    for char in service.characteristics:
                        if uuid_match(char.uuid, self.ESP32_CHARACTERISTIC_UUID):
                            characteristic = char
                            break
                    if characteristic:
                        break
                # 2) Jeśli nie ma – weź pierwszą notify/read, ale nie nazwę urządzenia (nimble)
                if not characteristic:
                    for service in services:
                        for char in service.characteristics:
                            if uuid_short(char.uuid) in skip_uuids:
                                continue
                            if "notify" in char.properties or "read" in char.properties:
                                characteristic = char
                                break
                        if characteristic:
                            break
                
                if characteristic:
                    # Enable notifications if supported
                    if "notify" in characteristic.properties:
                        await self.client.start_notify(characteristic.uuid, self._notification_handler)
                        print("[BLE] Subskrypcja: powiadomienia (notify)", flush=True)
                    else:
                        asyncio.create_task(self._poll_data(characteristic))
                        print("[BLE] Subskrypcja: odczyt co 100 ms (poll)", flush=True)
                else:
                    try:
                        await self.client.start_notify(self.ESP32_CHARACTERISTIC_UUID, self._notification_handler)
                        print("[BLE] Subskrypcja: powiadomienia (UUID domyślne)", flush=True)
                    except Exception:
                        asyncio.create_task(self._poll_data_by_uuid())
                        print("[BLE] Subskrypcja: odczyt co 100 ms (UUID domyślne)", flush=True)
                        
        except Exception as e:
            logging.error(f"Connection error: {e}")
            self.connected = False
            self.connection_status.emit(False, f"Connection error: {str(e)}")
    
    def _notification_handler(self, sender, data):
        """Handle incoming notifications from ESP32"""
        try:
            if not data:
                return
            # Zawsze wypisz co przyszło (i wymuś flush), żeby w terminalu coś było widać
            try:
                text = data.decode('utf-8').strip()
                preview = repr(text)[:60]
            except Exception:
                preview = ' '.join(f'{b:02x}' for b in data[:20])
            print(f"[BLE] odebrano: {preview}", flush=True)
            sys.stdout.flush()

            try:
                text = data.decode('utf-8').strip()
                heading = self._parse_heading(text)
                if heading is not None:
                    print(f"Azymut: {heading}°", flush=True)
                    sys.stdout.flush()
                    self.heading_received.emit(heading)
                    return
            except Exception:
                pass
            if len(data) >= 2:
                heading = int.from_bytes(data[:2], byteorder='little')
                if 0 <= heading <= 359:
                    print(f"Azymut: {heading}°", flush=True)
                    sys.stdout.flush()
                    self.heading_received.emit(heading)
                elif 0 <= heading <= 360:
                    h = 0 if heading == 360 else heading
                    print(f"Azymut: {h}°", flush=True)
                    sys.stdout.flush()
                    self.heading_received.emit(h)
        except Exception as e:
            logging.error(f"Notification handler error: {e}")
    
    async def _poll_data(self, characteristic):
        """Poll for data if notifications are not available"""
        while self.running and self.connected:
            try:
                if self.client and self.client.is_connected:
                    data = await self.client.read_gatt_char(characteristic.uuid)
                    self._notification_handler(characteristic.uuid, data)
                await asyncio.sleep(0.1)  # Poll every 100ms
            except Exception as e:
                logging.error(f"Poll error: {e}")
                await asyncio.sleep(1)
    
    async def _poll_data_by_uuid(self):
        """Poll using default UUID"""
        while self.running and self.connected:
            try:
                if self.client and self.client.is_connected:
                    data = await self.client.read_gatt_char(self.ESP32_CHARACTERISTIC_UUID)
                    self._notification_handler(self.ESP32_CHARACTERISTIC_UUID, data)
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.error(f"Poll by UUID error: {e}")
                await asyncio.sleep(1)
    
    def _parse_heading(self, text):
        """Parse heading value from text data"""
        # Liczby 0-359 lub 0-360, także z kropką (np. 45.7)
        # Formaty: "heading: 123", "123", "H:123", "45.7"
        parts = re.findall(r'\d+\.?\d*', text)
        for num_str in parts:
            try:
                num = int(round(float(num_str)))
                if num == 360:
                    num = 0
                if 0 <= num <= 359:
                    return num
            except ValueError:
                continue
        return None
    
    def stop(self):
        """Stop the Bluetooth handler"""
        self.running = False
        if self.loop and self.loop.is_running():
            # Schedule disconnect in the event loop
            asyncio.run_coroutine_threadsafe(self._disconnect(), self.loop)
            # Give it a moment to disconnect
            import time
            time.sleep(0.5)
            # Stop the event loop
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()
    
    async def _disconnect(self):
        """Disconnect from ESP32"""
        try:
            if self.client and self.client.is_connected:
                await self.client.disconnect()
            self.connected = False
            self.connection_status.emit(False, "Disconnected")
        except Exception as e:
            logging.error(f"Disconnect error: {e}")

