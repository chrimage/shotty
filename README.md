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
- **Window Activation**: Focus specific windows before capture
- **MCP Integration**: FastMCP-based server for LLM integration
- **Base64 Encoding**: Images ready for multimodal LLM consumption

### GNOME Wayland Support
- Primary method: window-calls GNOME extension
- Fallback: Process-based window detection
- Screenshot methods: gnome-screenshot, ImageMagick

## 📋 Prerequisites

### Required
- GNOME Shell on Wayland
- Python 3.8+
- `gnome-screenshot` utility

### Recommended Extensions
- [window-calls](https://extensions.gnome.org/extension/4724/window-calls/) - Enables true window-specific capture and listing

## 🛠️ Installation

```bash
# Clone the repository
git clone https://github.com/chrimage/shotty.git
cd shotty

# Install dependencies
pip install fastmcp

# Install GNOME extension (recommended)
# Visit: https://extensions.gnome.org/extension/4724/window-calls/
```

## 🔧 Usage

### As MCP Server
```bash
python server.py
```

### Available Tools
- `list_windows()` - Get all visible windows
- `capture_screenshot(window_id=None, include_cursor=False)` - Capture screenshots

## 🏗️ Architecture

The server implements a dual-approach strategy:

1. **Primary**: GNOME extension integration for accurate window data
2. **Fallback**: Process-based detection for basic functionality
3. **Screenshot**: Multiple capture methods with automatic fallback

## ⚡ Quick Test

```python
# Test window listing
python -c "from server import _list_windows_via_extension; print(_list_windows_via_extension())"

# Test screenshot capture
python -c "from server import _capture_window_by_id; _capture_window_by_id('WINDOW_ID')"
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