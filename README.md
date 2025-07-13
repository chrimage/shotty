# Shotty 📸

> **⚠️ ACTIVE DEVELOPMENT** - This project is currently under active development. Core technical challenges have been solved, but the implementation is still evolving. Expect breaking changes and incomplete features.

A Model Context Protocol (MCP) server that provides screenshot capture and window management tools for GNOME Wayland environments. Designed specifically for multimodal LLMs that need to "see" desktop content.

## 🎯 Project Status

- ✅ **Core Technical Challenges Solved**
- ✅ Window listing via GNOME extensions
- ✅ Window-specific screenshot capture
- ✅ Base64 image encoding for LLM consumption
- 🚧 **In Active Development** - APIs and features may change

## 🚀 Features

### Current Capabilities
- **Window Listing**: Enumerate all visible windows on GNOME desktop
- **Screenshot Capture**: Full screen and window-specific screenshots
- **Window State Management**: Remember and restore active windows during capture
- **XDG Portal Integration**: Modern, secure screenshot capture with user permissions
- **Window Activation**: Focus specific windows before capture
- **MCP Integration**: FastMCP-based server for LLM integration
- **Base64 Encoding**: Images ready for multimodal LLM consumption

### GNOME Wayland Support
- **Primary**: XDG Desktop Portal (modern, secure, requires user permission)
- **Secondary**: GNOME Shell D-Bus API via window-calls extension  
- **Fallback**: Legacy tools (gnome-screenshot, ImageMagick)
- **Optimized UX**: Automatic window state restoration after captures

## 📋 Prerequisites

### Required
- GNOME Shell on Wayland (GNOME 42+)
- Python 3.10+
- `gnome-screenshot` utility

### Python Dependencies
- `fastmcp>=1.2.0` (core MCP functionality)
- `PyGObject>=3.42.0` (XDG Portal integration)
- `pydbus>=0.6.0` (D-Bus communication)

### System Packages (Ubuntu/Debian)
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 libgirepository1.0-dev
```

### Recommended Extensions
- [window-calls](https://extensions.gnome.org/extension/4724/window-calls/) - Enables true window-specific capture and listing

## 🛠️ Installation

### Quick Start with uvx (Recommended)

```bash
# Run directly from GitHub (no installation needed)
uvx --from https://github.com/chrimage/shotty.git shotty

# Or install locally for persistent use
uv tool install shotty --from https://github.com/chrimage/shotty.git
shotty
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/chrimage/shotty.git
cd shotty

# Install system packages (Ubuntu/Debian)
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 libgirepository1.0-dev

# Run with uv
uv run shotty

# Or install dependencies manually
pip install fastmcp PyGObject>=3.42.0 pydbus>=0.6.0
python server.py
```

### System Requirements

- GNOME Shell on Wayland (GNOME 42+)
- Python 3.10+
- System packages: `python3-gi python3-gi-cairo gir1.2-gtk-4.0 libgirepository1.0-dev`

### Recommended Extensions

- [window-calls](https://extensions.gnome.org/extension/4724/window-calls/) - Enables true window-specific capture and listing

## 🔧 Usage

### As MCP Server
```bash
# With uvx (recommended)
uvx --from https://github.com/chrimage/shotty.git shotty

# With uv (from local directory)
uv run shotty

# Traditional method
python server.py
```

### Available Tools
- `list_windows()` - Get all visible windows
- `capture_screenshot(window_id=None, include_cursor=False)` - Capture screenshots

### Development with Claude Code

To test Shotty with Claude Code, add it as an MCP server:

```bash
# Add the server to Claude Code using uvx
claude mcp add shotty uvx --from https://github.com/chrimage/shotty.git shotty

# Or using local path
claude mcp add shotty python /path/to/shotty/server.py

# Verify the server is added
claude mcp list

# Test in Claude Code
# Use the tools directly: list_windows() and capture_screenshot()
```

#### Expected Behavior
- **Window Listing**: Returns JSON array of windows with IDs and titles
- **Screenshot Capture**: Returns images that display directly in Claude Code
- **Window-Specific Capture**: Focuses target window, then captures it
- **Storage**: Screenshots saved to `~/Pictures/shotty/` directory

#### Permissions & First Run
- **XDG Portal**: First screenshot may show permission dialog - grant access for persistent permissions
- **Extension Required**: Window-specific features need the window-calls GNOME extension
- **User Interaction**: Some portal operations require active window/user interaction

#### Troubleshooting
- Ensure the window-calls GNOME extension is installed and enabled
- Check that `gnome-screenshot` is available in your PATH
- Verify Python dependencies are installed: `pip install fastmcp PyGObject pydbus`
- For "Permission denied" errors, try taking a screenshot manually first to grant portal permissions

## 🏗️ Architecture

The server implements a dual-approach strategy:

1. **Primary**: GNOME extension integration for accurate window data
2. **Fallback**: Process-based detection for basic functionality
3. **Screenshot**: Multiple capture methods with automatic fallback

## ⚡ Quick Test

### Standalone Testing
```python
# Test window listing
python -c "from server import _list_windows_via_extension; print(_list_windows_via_extension())"

# Test full screen capture (creates Image object)
python -c "from server import _capture_full_screen; from fastmcp.utilities.types import Image; import base64; data=_capture_full_screen(); img=Image(data=base64.b64decode(data), format='image/png'); print(f'Created {len(img.data)} byte image')"
```

### MCP Integration Testing
```bash
# Add to Claude Code using uvx (recommended)
claude mcp add shotty uvx --from https://github.com/chrimage/shotty.git shotty

# Or using local path (replace with your actual path)
claude mcp add shotty python /home/chris/code/mcp-servers/shotty/server.py

# In Claude Code, test with:
# list_windows()
# capture_screenshot()
# capture_screenshot(window_id="WINDOW_ID_FROM_LIST")
```

## 🐛 Known Limitations

- **Wayland Security**: Some window operations require GNOME extensions
- **Extension Dependency**: Best functionality requires window-calls extension
- **Development Status**: APIs may change without notice

## 🤝 Contributing

This project is in **active development**. Core technical challenges have been solved, but the implementation is rapidly evolving.

- 🔬 **Research Phase**: Understanding GNOME Wayland capabilities
- 🛠️ **Implementation Phase**: Building robust capture mechanisms  
- 🧪 **Testing Phase**: Validating with multimodal LLMs

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- Built with [FastMCP](https://gofastmcp.com) framework
- GNOME Shell extension ecosystem
- Model Context Protocol specification

---

**⚠️ Remember**: This project is under active development. Star and watch for updates!