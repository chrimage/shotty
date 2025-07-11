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
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

# Configure logging to stderr (captured by MCP host client)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)

logger = logging.getLogger(__name__)

# Screenshot storage configuration
SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"
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
    try:
        if window_id:
            # Try to capture a specific window
            base64_data = _capture_window_by_id(window_id, include_cursor)
        else:
            # Capture full screen
            base64_data = _capture_full_screen(include_cursor)
        
        # Convert base64 to bytes and return as Image object for multimodal LLM consumption
        image_bytes = base64.b64decode(base64_data)
        return Image(data=image_bytes, format="image/png")
            
    except Exception as e:
        error_msg = f"Screenshot capture failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

def _capture_full_screen(include_cursor: bool = False) -> str:
    """Capture the full screen and return as base64-encoded PNG."""
    logger.info("Capturing full screen screenshot")
    
    # Generate filename with timestamp
    timestamp = int(time.time())
    filename = f"screenshot_full_{timestamp}.png"
    filepath = SCREENSHOTS_DIR / filename
    
    # Try different screenshot methods in order of preference
    screenshot_methods = [
        _try_grim_full,
        _try_gnome_screenshot_full,
        _try_import_full,
    ]
    
    for method in screenshot_methods:
        try:
            method(filepath, include_cursor)
            if filepath.exists():
                # Read and encode the image
                with open(filepath, 'rb') as f:
                    image_data = f.read()
                    
                # Convert to base64
                image_b64 = base64.b64encode(image_data).decode('utf-8')
                
                logger.info(f"Successfully captured full screen to {filepath}")
                return image_b64
                
        except Exception as e:
            logger.warning(f"Screenshot method {method.__name__} failed: {e}")
            continue
    
    raise RuntimeError("All screenshot methods failed for full screen capture")

def _capture_window_by_id(window_id: str, include_cursor: bool = False) -> str:
    """Capture a specific window and return as base64-encoded PNG."""
    logger.info(f"Capturing window with ID: {window_id}")
    
    # Generate filename with timestamp
    timestamp = int(time.time())
    filename = f"screenshot_window_{window_id}_{timestamp}.png"
    filepath = SCREENSHOTS_DIR / filename
    
    # Try GNOME-specific geometry detection first
    geometry = _get_window_geometry_gnome(window_id)
    
    if geometry:
        # Use grim with exact geometry
        try:
            _try_grim_with_geometry(filepath, geometry, include_cursor)
            
            # Read and encode the image
            with open(filepath, 'rb') as f:
                image_data = f.read()
                
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            logger.info(f"Successfully captured window {window_id} using geometry")
            return image_b64
            
        except Exception as e:
            logger.warning(f"Geometry-based capture failed: {e}")
    
    # Fallback to interactive selection or focus-based capture
    try:
        # Try to focus the window (this might not work without extensions)
        _try_focus_window(window_id)
        
        # Give the window more time to come to focus and settle
        time.sleep(1.5)
        
        # Capture the active window
        return _capture_active_window(filepath, include_cursor)
        
    except Exception as e:
        logger.warning(f"Window focus failed: {e}, falling back to full screen")
        # Fallback to full screen if window-specific capture fails
        return _capture_full_screen(include_cursor)

def _capture_active_window(filepath: Path, include_cursor: bool = False) -> str:
    """Capture the currently active window."""
    logger.info("Capturing active window")
    
    # Try different methods for active window capture
    window_methods = [
        lambda fp, ic: _try_grim_window_interactive(fp, ic),
        _try_gnome_screenshot_window,
        _try_import_active_window,
    ]
    
    for method in window_methods:
        try:
            method(filepath, include_cursor)
            if filepath.exists():
                # Read and encode the image
                with open(filepath, 'rb') as f:
                    image_data = f.read()
                    
                # Convert to base64
                image_b64 = base64.b64encode(image_data).decode('utf-8')
                
                logger.info(f"Successfully captured active window to {filepath}")
                return image_b64
                
        except Exception as e:
            logger.warning(f"Window capture method {method.__name__} failed: {e}")
            continue
    
    raise RuntimeError("All window capture methods failed")

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