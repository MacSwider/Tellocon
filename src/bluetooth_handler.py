import asyncio
import logging
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
    
    # Common ESP32 BLE service UUIDs
    ESP32_SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
    ESP32_CHARACTERISTIC_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
    
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
                
                # Try to find the characteristic
                services = await self.client.get_services()
                characteristic = None
                
                # Look for the characteristic that can notify
                for service in services:
                    for char in service.characteristics:
                        if "notify" in char.properties or "read" in char.properties:
                            characteristic = char
                            break
                    if characteristic:
                        break
                
                if characteristic:
                    # Enable notifications if supported
                    if "notify" in characteristic.properties:
                        await self.client.start_notify(characteristic.uuid, self._notification_handler)
                    else:
                        # If notify not available, poll for data
                        asyncio.create_task(self._poll_data(characteristic))
                else:
                    # Try default UUIDs
                    try:
                        await self.client.start_notify(self.ESP32_CHARACTERISTIC_UUID, self._notification_handler)
                    except:
                        # If that fails, try to read from it periodically
                        asyncio.create_task(self._poll_data_by_uuid())
                        
        except Exception as e:
            logging.error(f"Connection error: {e}")
            self.connected = False
            self.connection_status.emit(False, f"Connection error: {str(e)}")
    
    def _notification_handler(self, sender, data):
        """Handle incoming notifications from ESP32"""
        try:
            if data:
                # Try to decode as text
                try:
                    text = data.decode('utf-8').strip()
                    heading = self._parse_heading(text)
                    if heading is not None:
                        self.heading_received.emit(heading)
                except:
                    # Try to parse as binary data
                    if len(data) >= 2:
                        # Assume 16-bit integer (0-359)
                        heading = int.from_bytes(data[:2], byteorder='little')
                        if 0 <= heading <= 359:
                            self.heading_received.emit(heading)
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
        # Look for numbers in range 0-359
        # Common formats: "heading: 123", "123", "H:123", etc.
        numbers = re.findall(r'\d+', text)
        for num_str in numbers:
            num = int(num_str)
            if 0 <= num <= 359:
                return num
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

