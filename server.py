#!/usr/bin/env python3
"""
Screenshot MCP Server

A Model Context Protocol server that provides tools for capturing screenshots
and listing windows in GNOME Wayland environments.
"""

import base64
import json
import logging
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib, Gio
    PYGOBJECT_AVAILABLE = True
except ImportError:
    PYGOBJECT_AVAILABLE = False
    pass  # Will log warning after logger is configured

try:
    import pydbus
    PYDBUS_AVAILABLE = True
except ImportError:
    PYDBUS_AVAILABLE = False
    pass  # Will log warning after logger is configured

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

# Configure logging to stderr (captured by MCP host client)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)

logger = logging.getLogger(__name__)

# Log warnings for missing optional dependencies
if not PYGOBJECT_AVAILABLE:
    logger.warning("PyGObject not available, portal backend disabled")
if not PYDBUS_AVAILABLE:
    logger.warning("pydbus not available, portal backend disabled")

# Screenshot storage configuration
SCREENSHOTS_DIR = Path.home() / "Pictures" / "shotty"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Create the FastMCP server instance
mcp = FastMCP(name="Screenshot Server")

# Data model for Window
class Window:
    """Represents a capturable application window on the desktop."""
    
    def __init__(self, id: str, title: str):
        self.id = id
        self.title = title
    
    def to_dict(self) -> Dict[str, str]:
        """Convert window to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title
        }

# Abstract base class for screenshot backends
class ScreenshotBackend(ABC):
    """Abstract base class for different screenshot capture methods."""
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available on the current system."""
        pass
    
    @abstractmethod
    def capture_screen(self, filepath: Path, include_cursor: bool = False) -> bool:
        """Capture the full screen. Returns True on success."""
        pass
    
    @abstractmethod
    def capture_window(self, filepath: Path, window_id: str, include_cursor: bool = False) -> bool:
        """Capture a specific window. Returns True on success."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this backend."""
        pass

class XDGPortalBackend(ScreenshotBackend):
    """XDG Desktop Portal backend for screenshot capture."""
    
    def __init__(self):
        self._bus = None
        self._portal = None
        self._initialized = False
    
    def _initialize(self) -> bool:
        """Initialize D-Bus connection to portal."""
        if self._initialized:
            return True
            
        if not (PYGOBJECT_AVAILABLE and PYDBUS_AVAILABLE):
            return False
            
        try:
            self._bus = pydbus.SessionBus()
            self._portal = self._bus.get("org.freedesktop.portal.Desktop")
            self._initialized = True
            logger.info("XDG Portal backend initialized successfully")
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize XDG Portal backend: {e}")
            return False
    
    def is_available(self) -> bool:
        """Check if XDG Portal is available."""
        return self._initialize()
    
    def capture_screen(self, filepath: Path, include_cursor: bool = False) -> bool:
        """Capture screen using XDG Portal."""
        if not self._initialize():
            return False
            
        try:
            # Request screenshot through portal
            options = {
                "interactive": False,  # Don't show UI for area selection
                "modal": True,         # Make permission dialog modal
            }
            
            logger.info("Requesting screenshot through XDG Portal (may show permission dialog)")
            
            # Call Screenshot method - this may show a permission dialog
            response = self._portal.Screenshot("", options,
                                             dbus_interface="org.freedesktop.portal.Screenshot")
            
            if response and 'uri' in response:
                # Portal returns a URI to the screenshot file
                screenshot_uri = response['uri']
                
                # Convert URI to local path and copy to desired location
                if self._copy_portal_screenshot(screenshot_uri, filepath):
                    logger.info(f"Successfully captured screen via XDG Portal to {filepath}")
                    return True
                else:
                    logger.error("Failed to copy screenshot from portal temporary location")
            else:
                logger.warning("XDG Portal screenshot request was denied or failed")
                    
        except Exception as e:
            # Handle specific portal errors
            error_msg = str(e).lower()
            if "permission denied" in error_msg or "not allowed" in error_msg:
                logger.error("Screenshot permission denied by user or portal")
            elif "cancelled" in error_msg or "user cancelled" in error_msg:
                logger.info("Screenshot cancelled by user")
            elif "timeout" in error_msg:
                logger.error("Screenshot request timed out")
            else:
                logger.warning(f"XDG Portal screen capture failed: {e}")
            
        return False
    
    def capture_window(self, filepath: Path, window_id: str, include_cursor: bool = False) -> bool:
        """Capture window using XDG Portal (interactive mode)."""
        if not self._initialize():
            return False
            
        try:
            # For window capture, we need interactive mode
            options = {
                "interactive": True,   # Show UI for window selection
                "modal": True,        # Make dialog modal
            }
            
            logger.info("Portal will show window selection dialog...")
            response = self._portal.Screenshot("", options,
                                             dbus_interface="org.freedesktop.portal.Screenshot")
            
            if response and 'uri' in response:
                screenshot_uri = response['uri']
                
                if self._copy_portal_screenshot(screenshot_uri, filepath):
                    logger.info(f"Successfully captured window via XDG Portal to {filepath}")
                    return True
                    
        except Exception as e:
            logger.warning(f"XDG Portal window capture failed: {e}")
            
        return False
    
    def _copy_portal_screenshot(self, uri: str, destination: Path) -> bool:
        """Copy screenshot from portal URI to destination."""
        try:
            # Convert portal URI to local file path
            if uri.startswith('file://'):
                source_path = uri[7:]  # Remove 'file://' prefix
            else:
                logger.error(f"Unsupported portal URI format: {uri}")
                return False
                
            # Copy file to destination
            import shutil
            shutil.copy2(source_path, destination)
            
            # Clean up portal temporary file
            try:
                Path(source_path).unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up portal temp file: {e}")
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy portal screenshot: {e}")
            return False
    
    @property
    def name(self) -> str:
        return "XDG Desktop Portal"

class GNOMEShellBackend(ScreenshotBackend):
    """GNOME Shell backend using gnome-screenshot and grim."""
    
    def is_available(self) -> bool:
        """Check if GNOME Shell tools are available."""
        tools = ['gnome-screenshot', 'grim']
        for tool in tools:
            try:
                subprocess.run([tool, '--version'], capture_output=True, timeout=2)
                return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        return False
    
    def capture_screen(self, filepath: Path, include_cursor: bool = False) -> bool:
        """Capture screen using GNOME tools."""
        methods = [
            self._try_grim_full,
            self._try_gnome_screenshot_full,
            self._try_import_full,
        ]
        
        for method in methods:
            try:
                method(filepath, include_cursor)
                if filepath.exists():
                    return True
            except Exception as e:
                logger.warning(f"Method {method.__name__} failed: {e}")
                continue
        return False
    
    def capture_window(self, filepath: Path, window_id: str, include_cursor: bool = False) -> bool:
        """Capture window using GNOME tools with focusing."""
        try:
            # Try geometry-based capture first
            geometry = _get_window_geometry_gnome(window_id)
            if geometry:
                self._try_grim_with_geometry(filepath, geometry, include_cursor)
                if filepath.exists():
                    return True
            
            # Fallback to focus-based capture
            _try_focus_window(window_id)
            time.sleep(0.2)  # Brief delay for window focus
            
            methods = [
                self._try_gnome_screenshot_window,
                lambda fp, ic: self._try_grim_window_interactive(fp, ic),
            ]
            
            for method in methods:
                try:
                    method(filepath, include_cursor)
                    if filepath.exists():
                        return True
                except Exception as e:
                    logger.warning(f"Window capture method {method.__name__} failed: {e}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Window capture failed: {e}")
            
        return False
    
    def _try_grim_full(self, filepath: Path, include_cursor: bool = False):
        """Try capturing full screen with grim."""
        cmd = ["grim"]
        if include_cursor:
            cmd.extend(["-c"])
        cmd.append(str(filepath))
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(f"grim failed: {result.stderr}")
    
    def _try_gnome_screenshot_full(self, filepath: Path, include_cursor: bool = False):
        """Try capturing full screen with gnome-screenshot."""
        cmd = ["/usr/bin/gnome-screenshot"]
        if include_cursor:
            cmd.append("--include-pointer")
        cmd.extend(["--file", str(filepath)])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(f"gnome-screenshot failed: {result.stderr}")
    
    def _try_import_full(self, filepath: Path, include_cursor: bool = False):
        """Try capturing full screen with ImageMagick import."""
        cmd = ["import", "-window", "root"]
        if not include_cursor:
            cmd.extend(["-strip"])
        cmd.append(str(filepath))
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(f"ImageMagick import failed: {result.stderr}")
    
    def _try_gnome_screenshot_window(self, filepath: Path, include_cursor: bool = False):
        """Try capturing active window with gnome-screenshot."""
        cmd = ["/usr/bin/gnome-screenshot", "--window"]
        if include_cursor:
            cmd.append("--include-pointer")
        cmd.extend(["--file", str(filepath)])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(f"gnome-screenshot window capture failed: {result.stderr}")
    
    def _try_grim_window_interactive(self, filepath: Path, include_cursor: bool = False):
        """Try capturing window using grim + slurp for interactive selection."""
        logger.info("Using grim + slurp for interactive window selection")
        
        slurp_result = subprocess.run(
            ['slurp'], capture_output=True, text=True, timeout=30
        )
        
        if slurp_result.returncode != 0:
            raise RuntimeError(f"slurp selection failed: {slurp_result.stderr}")
            
        geometry = slurp_result.stdout.strip()
        self._try_grim_with_geometry(filepath, geometry, include_cursor)
    
    def _try_grim_with_geometry(self, filepath: Path, geometry: str, include_cursor: bool = False):
        """Use grim with specific geometry coordinates."""
        cmd = ["grim", "-g", geometry]
        if include_cursor:
            cmd.extend(["-c"])
        cmd.append(str(filepath))
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(f"grim geometry capture failed: {result.stderr}")
    
    @property
    def name(self) -> str:
        return "GNOME Shell"

# Window state management
class WindowStateManager:
    """Manages window state for seamless switching during screenshots."""
    
    def __init__(self):
        self._previous_window = None
    
    def get_active_window(self) -> Optional[str]:
        """Get the currently active window ID."""
        try:
            # Get all windows and find the focused one
            cmd = [
                "gdbus", "call",
                "--session",
                "--dest", "org.gnome.Shell",
                "--object-path", "/org/gnome/Shell/Extensions/Windows",
                "--method", "org.gnome.Shell.Extensions.Windows.List"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                # Parse the response
                import ast
                import json
                dbus_tuple = ast.literal_eval(result.stdout.strip())
                json_string = dbus_tuple[0]
                windows_data = json.loads(json_string)
                
                # Find the window with focus
                for window_data in windows_data:
                    if window_data.get('focus', False):
                        return str(window_data['id'])
                        
                # If no window has focus, try to find the most recently active normal window
                for window_data in windows_data:
                    if (window_data.get('frame_type') == 0 and 
                        window_data.get('window_type') == 0):
                        return str(window_data['id'])
                    
        except Exception as e:
            logger.warning(f"Failed to get active window: {e}")
            
        return None
    
    def remember_active_window(self):
        """Remember the currently active window for later restoration."""
        self._previous_window = self.get_active_window()
        if self._previous_window:
            logger.info(f"Remembered active window: {self._previous_window}")
        else:
            logger.warning("Could not detect active window to remember")
    
    def restore_previous_window(self):
        """Restore focus to the previously active window."""
        if self._previous_window:
            try:
                logger.info(f"Attempting to restore focus to window: {self._previous_window}")
                _try_focus_window(self._previous_window)
                logger.info(f"Successfully restored focus to window: {self._previous_window}")
                self._previous_window = None  # Clear after use
            except Exception as e:
                logger.warning(f"Failed to restore previous window: {e}")
        else:
            logger.info("No previous window to restore")

# Global window state manager
window_state_manager = WindowStateManager()

# Backend manager
class BackendManager:
    """Manages multiple screenshot backends with automatic fallback."""
    
    def __init__(self):
        self.backends = [
            XDGPortalBackend(),
            GNOMEShellBackend(),
        ]
    
    def get_available_backend(self) -> Optional[ScreenshotBackend]:
        """Get the first available backend."""
        for backend in self.backends:
            if backend.is_available():
                logger.info(f"Using backend: {backend.name}")
                return backend
        return None
    
    def capture_screen(self, filepath: Path, include_cursor: bool = False) -> bool:
        """Capture screen using first available backend."""
        for backend in self.backends:
            if backend.is_available():
                try:
                    if backend.capture_screen(filepath, include_cursor):
                        logger.info(f"Successfully captured screen using {backend.name}")
                        return True
                except Exception as e:
                    logger.warning(f"Backend {backend.name} failed: {e}")
                    continue
        return False
    
    def capture_window(self, filepath: Path, window_id: str, include_cursor: bool = False) -> bool:
        """Capture window using first available backend."""
        for backend in self.backends:
            if backend.is_available():
                try:
                    if backend.capture_window(filepath, window_id, include_cursor):
                        logger.info(f"Successfully captured window using {backend.name}")
                        return True
                except Exception as e:
                    logger.warning(f"Backend {backend.name} failed: {e}")
                    continue
        return False

# Global backend manager
backend_manager = BackendManager()

@mcp.tool
def list_windows() -> str:
    """
    List all open, non-minimized windows on the GNOME desktop.
    
    Returns a list of window objects, each containing:
    - id: A unique identifier for the window that can be used for capture
    - title: The human-readable title of the window
    
    This implementation tries multiple methods:
    1. window-calls GNOME extension (if available)
    2. Fallback to process-based detection
    """
    try:
        # First try: window-calls extension
        return _list_windows_via_extension()
    except Exception as e:
        logger.warning(f"Window-calls extension not available: {e}")
        
        # Fallback: Use process-based detection
        try:
            return _list_windows_via_processes()
        except Exception as fallback_e:
            logger.error(f"Fallback method also failed: {fallback_e}")
            raise RuntimeError("Unable to list windows: No supported method available")

def _list_windows_via_extension() -> str:
    """Try to list windows using the window-calls GNOME extension."""
    cmd = [
        "gdbus", "call",
        "--session",
        "--dest", "org.gnome.Shell",
        "--object-path", "/org/gnome/Shell/Extensions/Windows", 
        "--method", "org.gnome.Shell.Extensions.Windows.List"
    ]
    
    logger.info(f"Executing command: {' '.join(cmd)}")
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10  # 10 second timeout
    )
    
    if result.returncode != 0:
        error_msg = f"Failed to list windows via extension: {result.stderr.strip()}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    # Parse the JSON response from the D-Bus call
    raw_output = result.stdout.strip()
    logger.info(f"Raw D-Bus output: {raw_output}")
    
    # D-Bus returns a tuple format like ('[{...}]',) - extract the JSON string
    try:
        # Parse the D-Bus tuple format
        import ast
        dbus_tuple = ast.literal_eval(raw_output)
        json_string = dbus_tuple[0]  # Get the first element (JSON string)
        
        # Parse the JSON array of window objects
        windows_data = json.loads(json_string)
    except (ValueError, json.JSONDecodeError, IndexError) as e:
        error_msg = f"Failed to parse window list JSON: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    # Filter for visible windows (frame_type=0, window_type=0) and convert to our format
    windows = []
    for window_data in windows_data:
        # Only include normal windows (not dialogs, menus, etc.)
        if (window_data.get('frame_type') == 0 and 
            window_data.get('window_type') == 0):
            
            window = Window(
                id=str(window_data['id']),
                title=window_data.get('wm_class', 'Unknown')
            )
            windows.append(window.to_dict())
    
    logger.info(f"Found {len(windows)} visible windows via extension")
    return json.dumps(windows)

def _list_windows_via_processes() -> str:
    """Fallback method: List windows based on running GUI processes."""
    logger.info("Using fallback process-based window detection")
    
    # Common GUI applications that create windows
    gui_processes = [
        'firefox', 'chrome', 'chromium', 'brave', 'opera',
        'gnome-terminal', 'konsole', 'xterm', 'alacritty',
        'code', 'codium', 'atom', 'sublime_text', 'vim', 'emacs',
        'nautilus', 'dolphin', 'thunar', 'ranger',
        'gimp', 'inkscape', 'blender', 'darktable',
        'libreoffice', 'writer', 'calc', 'impress',
        'evince', 'okular', 'zathura',
        'vlc', 'totem', 'mpv', 'rhythmbox',
        'discord', 'slack', 'telegram', 'signal',
        'thunderbird', 'evolution', 'claws-mail'
    ]
    
    try:
        # Get running processes
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            raise RuntimeError("Failed to get process list")
        
        # Parse process output and look for GUI applications
        windows = []
        lines = result.stdout.strip().split('\n')
        
        for line in lines[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 11:  # Valid process line
                command = parts[10]  # Command column
                
                # Extract process name (remove path)
                process_name = command.split('/')[-1]
                
                # Check if it's a GUI process
                for gui_proc in gui_processes:
                    if gui_proc in process_name.lower():
                        # Create a window entry
                        window = Window(
                            id=parts[1],  # Use PID as ID
                            title=process_name.title()
                        )
                        windows.append(window.to_dict())
                        break
        
        # Remove duplicates (same process name)
        seen_titles = set()
        unique_windows = []
        for window in windows:
            if window['title'] not in seen_titles:
                seen_titles.add(window['title'])
                unique_windows.append(window)
        
        logger.info(f"Found {len(unique_windows)} GUI applications via process detection")
        return json.dumps(unique_windows)
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout while listing processes")
    except Exception as e:
        raise RuntimeError(f"Process detection failed: {str(e)}")

@mcp.tool
def capture_screenshot(window_id: Optional[str] = None, include_cursor: bool = False) -> Image:
    """
    Capture a screenshot and return it as an image that multimodal LLMs can view.
    
    Args:
        window_id: Optional window ID to capture. If None, captures the full screen.
                  Use the ID from list_windows() to capture a specific window.
        include_cursor: Whether to include the mouse cursor in the screenshot.
    
    Returns:
        Image object containing PNG screenshot data for multimodal LLM viewing.
    
    Note: For specific window capture on Wayland, this will attempt to focus
    the window first, then capture the active window.
    """
    # Remember current active window for restoration (only for window-specific captures)
    if window_id:
        window_state_manager.remember_active_window()
    
    try:
        if window_id:
            # Try to capture a specific window (without double state management)
            base64_data = _capture_window_by_id_no_restore(window_id, include_cursor)
        else:
            # Capture full screen
            base64_data = _capture_full_screen(include_cursor)
        
        # Convert base64 to bytes and return as Image object for multimodal LLM consumption
        image_bytes = base64.b64decode(base64_data)
        return Image(data=image_bytes, format="png")
            
    except Exception as e:
        error_msg = f"Screenshot capture failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    finally:
        # Always restore previous window focus if we switched windows
        if window_id:
            window_state_manager.restore_previous_window()

def _capture_full_screen(include_cursor: bool = False) -> str:
    """Capture the full screen using backend manager."""
    logger.info("Capturing full screen screenshot")
    
    # Generate filename with timestamp
    timestamp = int(time.time())
    filename = f"screenshot_full_{timestamp}.png"
    filepath = SCREENSHOTS_DIR / filename
    
    # Use backend manager for capture
    if backend_manager.capture_screen(filepath, include_cursor):
        # Read and encode the image
        with open(filepath, 'rb') as f:
            image_data = f.read()
            
        # Convert to base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        logger.info(f"Successfully captured full screen to {filepath}")
        return image_b64
    else:
        raise RuntimeError("All screenshot methods failed for full screen capture")

def _capture_window_by_id(window_id: str, include_cursor: bool = False) -> str:
    """Capture a specific window with enhanced window state management."""
    logger.info(f"Capturing window with ID: {window_id}")
    
    # Remember current active window for restoration
    window_state_manager.remember_active_window()
    
    try:
        return _capture_window_by_id_no_restore(window_id, include_cursor)
    finally:
        # Always restore previous window focus
        window_state_manager.restore_previous_window()

def _capture_window_by_id_no_restore(window_id: str, include_cursor: bool = False) -> str:
    """Capture a specific window without window state management (used internally)."""
    logger.info(f"Capturing window with ID: {window_id} (no state management)")
    
    # Generate filename with timestamp
    timestamp = int(time.time())
    filename = f"screenshot_window_{window_id}_{timestamp}.png"
    filepath = SCREENSHOTS_DIR / filename
    
    # Use backend manager for capture
    if backend_manager.capture_window(filepath, window_id, include_cursor):
        # Read and encode the image
        with open(filepath, 'rb') as f:
            image_data = f.read()
            
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        logger.info(f"Successfully captured window {window_id}")
        return image_b64
    else:
        # Fallback to full screen capture
        logger.warning("Window capture failed, falling back to full screen")
        return _capture_full_screen(include_cursor)

# Legacy function kept for compatibility
def _capture_active_window(filepath: Path, include_cursor: bool = False) -> str:
    """Capture the currently active window (legacy function)."""
    # This is now handled by the backend manager
    active_window = window_state_manager.get_active_window()
    if active_window:
        if backend_manager.capture_window(filepath, active_window, include_cursor):
            with open(filepath, 'rb') as f:
                image_data = f.read()
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            return image_b64
    
    raise RuntimeError("Failed to capture active window")

def _try_focus_window(window_id: str):
    """Attempt to focus a window by its ID using window-calls extension."""
    logger.info(f"Attempting to focus window with ID: {window_id}")
    
    try:
        # Use window-calls extension Activate method
        cmd = [
            "gdbus", "call",
            "--session", 
            "--dest", "org.gnome.Shell",
            "--object-path", "/org/gnome/Shell/Extensions/Windows",
            "--method", "org.gnome.Shell.Extensions.Windows.Activate",
            window_id
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            logger.info(f"Successfully activated window {window_id}")
        else:
            logger.warning(f"Failed to activate window: {result.stderr}")
            raise RuntimeError(f"Window activation failed: {result.stderr}")
            
    except Exception as e:
        logger.warning(f"Window activation failed: {e}")
        raise e

def _try_gnome_screenshot_full(filepath: Path, include_cursor: bool = False):
    """Try capturing full screen with gnome-screenshot."""
    cmd = ["/usr/bin/gnome-screenshot"]
    
    if include_cursor:
        cmd.append("--include-pointer")
    
    cmd.extend(["--file", str(filepath)])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode != 0:
        raise RuntimeError(f"gnome-screenshot failed: {result.stderr}")

def _try_gnome_screenshot_window(filepath: Path, include_cursor: bool = False):
    """Try capturing active window with gnome-screenshot."""
    cmd = ["/usr/bin/gnome-screenshot", "--window"]
    
    if include_cursor:
        cmd.append("--include-pointer")
    
    cmd.extend(["--file", str(filepath)])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode != 0:
        raise RuntimeError(f"gnome-screenshot window capture failed: {result.stderr}")

def _try_import_full(filepath: Path, include_cursor: bool = False):
    """Try capturing full screen with ImageMagick import."""
    cmd = ["import", "-window", "root"]
    
    if not include_cursor:
        cmd.extend(["-strip"])  # Remove cursor if not wanted
    
    cmd.append(str(filepath))
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode != 0:
        raise RuntimeError(f"ImageMagick import failed: {result.stderr}")

def _try_import_active_window(filepath: Path, include_cursor: bool = False):
    """Try capturing active window with ImageMagick import (limited on Wayland)."""
    # This likely won't work well on Wayland, but included for completeness
    cmd = ["import"]
    
    if not include_cursor:
        cmd.extend(["-strip"])
    
    cmd.append(str(filepath))
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode != 0:
        raise RuntimeError(f"ImageMagick import window capture failed: {result.stderr}")

def _try_grim_full(filepath: Path, include_cursor: bool = False):
    """Try capturing full screen with grim."""
    cmd = ["grim"]
    
    if include_cursor:
        cmd.extend(["-c"])  # Include cursor
    
    cmd.append(str(filepath))
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode != 0:
        raise RuntimeError(f"grim full screen capture failed: {result.stderr}")

def _try_grim_window_interactive(filepath: Path, include_cursor: bool = False):
    """Try capturing window using grim + slurp for interactive selection."""
    logger.info("Using grim + slurp for interactive window selection")
    
    # Step 1: Use slurp to get user-selected coordinates
    logger.info("Please select the window area with your mouse...")
    slurp_result = subprocess.run(
        ['slurp'], 
        capture_output=True, text=True, timeout=30  # Give user time to select
    )
    
    if slurp_result.returncode != 0:
        raise RuntimeError(f"slurp selection failed: {slurp_result.stderr}")
        
    geometry = slurp_result.stdout.strip()
    logger.info(f"Selected geometry: {geometry}")
    
    # Step 2: Use grim with the selected geometry
    _try_grim_with_geometry(filepath, geometry, include_cursor)

def _try_grim_with_geometry(filepath: Path, geometry: str, include_cursor: bool = False):
    """Use grim with specific geometry coordinates."""
    cmd = ["grim", "-g", geometry]
    
    if include_cursor:
        cmd.extend(["-c"])
    
    cmd.append(str(filepath))
    
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=10
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"grim geometry capture failed: {result.stderr}")

def _get_window_geometry_gnome(window_id: str) -> Optional[str]:
    """
    Try to get window geometry from GNOME Shell via D-Bus.
    Returns geometry string like "100,200 800x600" or None if not found.
    """
    try:
        # Try to get window list with geometry info from GNOME Shell
        cmd = [
            "gdbus", "call",
            "--session",
            "--dest", "org.gnome.Shell",
            "--object-path", "/org/gnome/Shell/Extensions/Windows", 
            "--method", "org.gnome.Shell.Extensions.Windows.List"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode != 0:
            return None
            
        # Parse D-Bus tuple format
        raw_output = result.stdout.strip()
        import ast
        dbus_tuple = ast.literal_eval(raw_output)
        json_string = dbus_tuple[0]
        windows_data = json.loads(json_string)
        
        # Find window by ID and extract geometry
        for window_data in windows_data:
            if str(window_data.get('id')) == window_id:
                rect = window_data.get('rect', {})
                if rect:
                    return f"{rect['x']},{rect['y']} {rect['width']}x{rect['height']}"
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to get window geometry from GNOME: {e}")
        return None

if __name__ == "__main__":
    logger.info("Starting Screenshot MCP Server")
    mcp.run()