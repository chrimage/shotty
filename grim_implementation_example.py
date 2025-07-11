#!/usr/bin/env python3
"""
Example implementation of how grim + slurp would work for window-specific screenshots.
This shows what we COULD do if grim/slurp were available.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

def get_window_geometry_sway(window_pid: str) -> Optional[str]:
    """
    Get window geometry from Sway compositor using JSON IPC.
    Returns geometry string like "100,200 800x600" or None if not found.
    """
    try:
        # Get Sway window tree as JSON
        result = subprocess.run(
            ['swaymsg', '-t', 'get_tree'],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode != 0:
            return None
            
        # Parse JSON tree to find window by PID
        tree = json.loads(result.stdout)
        
        def find_window_by_pid(node, target_pid):
            """Recursively search for window with matching PID."""
            if isinstance(node, dict):
                # Check if this node has the target PID
                if node.get('pid') == int(target_pid):
                    rect = node.get('rect', {})
                    if rect:
                        return f"{rect['x']},{rect['y']} {rect['width']}x{rect['height']}"
                
                # Search child nodes
                for child in node.get('nodes', []):
                    result = find_window_by_pid(child, target_pid)
                    if result:
                        return result
                        
                # Search floating nodes
                for child in node.get('floating_nodes', []):
                    result = find_window_by_pid(child, target_pid)
                    if result:
                        return result
            
            return None
        
        return find_window_by_pid(tree, window_pid)
        
    except Exception as e:
        print(f"Failed to get window geometry: {e}")
        return None

def capture_window_with_grim(window_pid: str, output_path: Path) -> bool:
    """
    Capture specific window using grim + geometry detection.
    Returns True if successful, False otherwise.
    """
    try:
        # Method 1: Try to get exact window geometry
        geometry = get_window_geometry_sway(window_pid)
        
        if geometry:
            # Use exact geometry
            cmd = ['grim', '-g', geometry, str(output_path)]
            print(f"Using exact geometry: {geometry}")
        else:
            # Method 2: Fallback to interactive selection
            # This would prompt user to select the window area
            cmd = ['grim', '-g', '$(slurp)', str(output_path)]
            print("Using interactive selection (user must select window)")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        return result.returncode == 0 and output_path.exists()
        
    except Exception as e:
        print(f"grim capture failed: {e}")
        return False

def capture_window_with_slurp_interactive(output_path: Path) -> bool:
    """
    Let user interactively select window area with slurp.
    This is the most reliable method on any Wayland compositor.
    """
    try:
        # Step 1: Use slurp to get user-selected coordinates
        slurp_result = subprocess.run(
            ['slurp'], 
            capture_output=True, text=True, timeout=30  # Give user time to select
        )
        
        if slurp_result.returncode != 0:
            return False
            
        geometry = slurp_result.stdout.strip()
        
        # Step 2: Use grim with the selected geometry
        grim_result = subprocess.run(
            ['grim', '-g', geometry, str(output_path)],
            capture_output=True, text=True, timeout=10
        )
        
        return grim_result.returncode == 0 and output_path.exists()
        
    except Exception as e:
        print(f"Interactive capture failed: {e}")
        return False

# Example usage in MCP server:
def enhanced_capture_screenshot(window_id: str) -> str:
    """
    Enhanced version that would work with grim + slurp.
    """
    output_path = Path(f"/tmp/window_{window_id}.png")
    
    # Try different methods in order of preference
    methods = [
        lambda: capture_window_with_grim(window_id, output_path),
        lambda: capture_window_with_slurp_interactive(output_path),
        # Could add more fallback methods here
    ]
    
    for method in methods:
        try:
            if method():
                # Read and return base64-encoded image
                with open(output_path, 'rb') as f:
                    import base64
                    return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            print(f"Method failed: {e}")
            continue
    
    raise RuntimeError("All capture methods failed")

if __name__ == "__main__":
    # Example: Show how to get geometry for a specific PID
    test_pid = "12345"
    geometry = get_window_geometry_sway(test_pid)
    if geometry:
        print(f"Window {test_pid} geometry: {geometry}")
    else:
        print(f"Window {test_pid} not found or not in Sway")