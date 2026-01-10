"""
OpenCue - Audio Device Manager

Handles audio device enumeration and switching for silent recording.
Supports VB-Cable and other virtual audio devices.
"""

import subprocess
import json
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class DeviceType(Enum):
    PHYSICAL = "physical"
    VIRTUAL = "virtual"
    UNKNOWN = "unknown"


@dataclass
class AudioDevice:
    id: str
    name: str
    device_type: DeviceType
    is_default: bool = False

    def is_virtual_cable(self) -> bool:
        """Check if this is a virtual audio cable device"""
        virtual_keywords = [
            "vb-cable", "vb-audio", "virtual cable", "voicemeeter",
            "cable input", "cable output", "virtual audio"
        ]
        name_lower = self.name.lower()
        return any(kw in name_lower for kw in virtual_keywords)


class AudioDeviceManager:
    """Manages Windows audio devices for silent recording"""

    def __init__(self):
        self._original_device: Optional[AudioDevice] = None
        self._devices_cache: Optional[List[AudioDevice]] = None

    def get_devices(self, refresh: bool = False) -> List[AudioDevice]:
        """Get list of all audio output devices"""
        if self._devices_cache and not refresh:
            return self._devices_cache

        devices = []

        # Use PowerShell to enumerate audio devices
        ps_script = '''
        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        $null = [Windows.Media.Devices.MediaDevice, Windows.Media.Devices, ContentType=WindowsRuntime]
        $null = [Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType=WindowsRuntime]

        # Get audio render devices using Get-AudioDevice if available, otherwise use WMI
        try {
            Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' } | ForEach-Object {
                @{
                    id = $_.ID
                    name = $_.Name
                    is_default = $_.Default
                } | ConvertTo-Json -Compress
            }
        } catch {
            # Fallback: use WMI
            Get-CimInstance -Namespace "root\\cimv2" -ClassName Win32_SoundDevice | ForEach-Object {
                @{
                    id = $_.DeviceID
                    name = $_.Name
                    is_default = $false
                } | ConvertTo-Json -Compress
            }
        }
        '''

        try:
            # Try using AudioDeviceCmdlets module first (most reliable)
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-AudioDevice -List | Where-Object { $_.Type -eq "Playback" } | '
                 'Select-Object ID, Name, Default | ConvertTo-Json'],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                # Handle single device (not a list)
                if isinstance(data, dict):
                    data = [data]

                for d in data:
                    device_type = DeviceType.VIRTUAL if self._is_virtual_name(d.get('Name', '')) else DeviceType.PHYSICAL
                    devices.append(AudioDevice(
                        id=d.get('ID', ''),
                        name=d.get('Name', 'Unknown'),
                        device_type=device_type,
                        is_default=d.get('Default', False)
                    ))
        except Exception as e:
            print(f"[OpenCue] AudioDeviceCmdlets not available: {e}")

            # Fallback: use soundcard library if available
            try:
                import soundcard as sc
                default_speaker = sc.default_speaker()
                for speaker in sc.all_speakers():
                    device_type = DeviceType.VIRTUAL if self._is_virtual_name(speaker.name) else DeviceType.PHYSICAL
                    devices.append(AudioDevice(
                        id=speaker.id,
                        name=speaker.name,
                        device_type=device_type,
                        is_default=(speaker.id == default_speaker.id)
                    ))
            except Exception as e2:
                print(f"[OpenCue] soundcard fallback failed: {e2}")

        self._devices_cache = devices
        return devices

    def _is_virtual_name(self, name: str) -> bool:
        """Check if device name indicates a virtual device"""
        virtual_keywords = [
            "vb-cable", "vb-audio", "virtual", "voicemeeter",
            "cable input", "cable output"
        ]
        name_lower = name.lower()
        return any(kw in name_lower for kw in virtual_keywords)

    def get_default_device(self) -> Optional[AudioDevice]:
        """Get current default audio output device"""
        devices = self.get_devices()
        for device in devices:
            if device.is_default:
                return device
        return devices[0] if devices else None

    def find_virtual_cable(self) -> Optional[AudioDevice]:
        """Find VB-Cable or similar virtual audio device"""
        devices = self.get_devices(refresh=True)
        for device in devices:
            if device.is_virtual_cable():
                return device
        return None

    def set_default_device(self, device: AudioDevice) -> bool:
        """Set the default audio output device"""
        try:
            # Use AudioDeviceCmdlets to set default device
            result = subprocess.run(
                ['powershell', '-Command',
                 f'Set-AudioDevice -ID "{device.id}"'],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                print(f"[OpenCue] Set default audio device: {device.name}")
                # Refresh cache
                self._devices_cache = None
                return True
            else:
                print(f"[OpenCue] Failed to set device: {result.stderr}")
                return False

        except Exception as e:
            print(f"[OpenCue] Error setting audio device: {e}")
            return False

    def switch_to_virtual(self) -> bool:
        """Switch to virtual audio cable, saving original device"""
        # Get current device
        current_device = self.get_default_device()
        if not current_device:
            print("[OpenCue] Could not determine current audio device")
            return False

        # Find virtual cable
        virtual = self.find_virtual_cable()
        if not virtual:
            print("[OpenCue] No virtual audio cable found (install VB-Cable)")
            return False

        # Already on virtual?
        if current_device.is_virtual_cable():
            print("[OpenCue] Already using virtual audio device")
            # Don't overwrite _original_device if we're already on virtual
            # (it should still point to the real device from a previous switch)
            if not self._original_device:
                # Find a non-virtual device to restore to
                self._original_device = self._find_realtek_or_default()
            return True

        # Save original device before switching
        self._original_device = current_device

        # Switch to virtual
        if self.set_default_device(virtual):
            print(f"[OpenCue] Switched from '{self._original_device.name}' to '{virtual.name}'")
            return True

        return False

    def _find_realtek_or_default(self) -> Optional['AudioDevice']:
        """Find Realtek or any non-virtual output device"""
        devices = self.get_devices()  # Returns playback devices only

        # First look for Realtek
        for dev in devices:
            if 'realtek' in dev.name.lower():
                print(f"[OpenCue] Found Realtek device: {dev.name}")
                return dev

        # Otherwise find any non-virtual output device
        for dev in devices:
            if not dev.is_virtual_cable():
                print(f"[OpenCue] Found non-virtual device: {dev.name}")
                return dev

        return None

    def restore_original(self) -> bool:
        """Restore the original audio device"""
        if not self._original_device:
            print("[OpenCue] No original device to restore")
            return False

        if self.set_default_device(self._original_device):
            print(f"[OpenCue] Restored audio to: {self._original_device.name}")
            self._original_device = None
            return True

        return False

    def get_capture_device_id(self) -> Optional[str]:
        """Get the device ID to use for audio capture (loopback)"""
        # If we switched to virtual, capture from that
        virtual = self.find_virtual_cable()
        if virtual:
            return virtual.id

        # Otherwise use default
        default = self.get_default_device()
        return default.id if default else None


# Singleton instance
_device_manager: Optional[AudioDeviceManager] = None

def get_device_manager() -> AudioDeviceManager:
    """Get the audio device manager singleton"""
    global _device_manager
    if _device_manager is None:
        _device_manager = AudioDeviceManager()
    return _device_manager


def check_virtual_cable_installed() -> dict:
    """Check if VB-Cable is installed and return status"""
    manager = get_device_manager()
    virtual = manager.find_virtual_cable()

    return {
        "installed": virtual is not None,
        "device_name": virtual.name if virtual else None,
        "device_id": virtual.id if virtual else None,
        "install_url": "https://vb-audio.com/Cable/" if not virtual else None
    }
