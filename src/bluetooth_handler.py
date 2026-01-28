import asyncio
import logging
from bleak import BleakClient, BleakScanner
from PyQt5.QtCore import QThread, pyqtSignal
import re
import sys

# Fix Windows COM threading issues with PyQt5 and Bleak
if sys.platform == 'win32':
    try:
        from bleak.backends.winrt.utils import allow_sta
        allow_sta()
    except ImportError:
        pass

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
    message_received = pyqtSignal(str)  # Emits raw message from ESP32
    connection_status = pyqtSignal(bool, str)  # Emits (connected, message)
    
    # ESP32C6 BLE service UUIDs (matching the Arduino code)
    ESP32_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
    ESP32_CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
    
    def __init__(self, device_name_pattern="XIAO_ESP32C6"):
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
                
                # Wait a moment for services to be discovered
                await asyncio.sleep(0.5)
                
                # Access services - try property first (Bleak 1.1.1+), then method if available
                services = None
                try:
                    # In Bleak 1.1.1+, services is a property
                    services = self.client.services
                except AttributeError:
                    # Fallback: try get_services() method if it exists (older versions)
                    try:
                        if hasattr(self.client, 'get_services'):
                            services = await self.client.get_services()
                    except Exception as e:
                        logging.warning(f"Could not get services: {e}")
                
                characteristic = None
                
                # Try to find characteristic by UUID first (faster and more reliable)
                try:
                    # Direct access to characteristic by UUID from ESP32 code
                    await self.client.start_notify(self.ESP32_CHARACTERISTIC_UUID, self._notification_handler)
                    logging.info(f"Successfully started notifications on {self.ESP32_CHARACTERISTIC_UUID}")
                except Exception as e:
                    logging.warning(f"Could not start notify on UUID {self.ESP32_CHARACTERISTIC_UUID}: {e}")
                    
                    # Fallback: search through services if available
                    if services:
                        try:
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
                                    logging.info(f"Started notifications on characteristic {characteristic.uuid}")
                                else:
                                    # If notify not available, poll for data
                                    asyncio.create_task(self._poll_data(characteristic))
                            else:
                                # No suitable characteristic found, try polling by UUID
                                logging.warning("No suitable characteristic found, trying polling")
                                asyncio.create_task(self._poll_data_by_uuid())
                        except Exception as e2:
                            logging.error(f"Error searching services: {e2}")
                            asyncio.create_task(self._poll_data_by_uuid())
                    else:
                        # Services not available, try polling by UUID
                        logging.warning("Services not available, trying polling by UUID")
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
                    # Print message to console/terminal
                    print(f"[ESP32C6] Received message: {text}")
                    # Emit raw message (for potential future use)
                    self.message_received.emit(text)
                    # Try to parse heading
                    heading = self._parse_heading(text)
                    if heading is not None:
                        self.heading_received.emit(heading)
                except:
                    # Try to parse as binary data
                    if len(data) >= 2:
                        # Assume 16-bit integer (0-359)
                        heading = int.from_bytes(data[:2], byteorder='little')
                        if 0 <= heading <= 359:
                            # Print message to console/terminal
                            print(f"[ESP32C6] Received message (binary): {heading}")
                            # Emit as text message
                            self.message_received.emit(str(heading))
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

