#!/usr/bin/env python3
"""
Unit tests for the list_windows functionality.

These tests mock the subprocess calls to avoid requiring actual GNOME desktop
environment and window-calls extension during testing.
"""

import json
import subprocess
from unittest.mock import Mock, patch
import pytest

from fastmcp import Client


class TestListWindows:
    """Test cases for the list_windows tool."""
    
    @pytest.fixture
    def mock_windows_data(self):
        """Sample window data that would be returned by the window-calls extension."""
        return [
            {
                "id": 1234567890,
                "wm_class": "Firefox",
                "wm_class_instance": "firefox",
                "pid": 12345,
                "frame_type": 0,
                "window_type": 0,
                "width": 1920,
                "height": 1080,
                "x": 0,
                "y": 0,
                "in_current_workspace": True,
                "monitor": 0
            },
            {
                "id": 9876543210,
                "wm_class": "Terminal",
                "wm_class_instance": "gnome-terminal",
                "pid": 54321,
                "frame_type": 0,
                "window_type": 0,
                "width": 800,
                "height": 600,
                "x": 100,
                "y": 100,
                "in_current_workspace": True,
                "monitor": 0
            },
            {
                "id": 1111111111,
                "wm_class": "Dialog",
                "wm_class_instance": "dialog",
                "pid": 11111,
                "frame_type": 1,  # Not a normal window
                "window_type": 1,  # Not a normal window
                "width": 400,
                "height": 300,
                "x": 200,
                "y": 200,
                "in_current_workspace": True,
                "monitor": 0
            }
        ]
    
    @pytest.fixture
    def mcp_server(self):
        """Create a FastMCP server instance for testing."""
        # Import the server module to get the mcp instance
        import server
        return server.mcp
    
    @patch('server.subprocess.run')
    async def test_list_windows_success(self, mock_run, mock_windows_data, mcp_server):
        """Test successful window listing."""
        # Mock successful subprocess call
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(mock_windows_data),
            stderr=""
        )
        
        # Test the tool via MCP client
        async with Client(mcp_server) as client:
            result = await client.call_tool("list_windows", {})
            
            # Parse the result - FastMCP returns JSON string in content
            windows = json.loads(result.content[0].text)
            
            # Should only return normal windows (frame_type=0, window_type=0)
            assert len(windows) == 2
            
            # Check first window
            assert windows[0]["id"] == "1234567890"
            assert windows[0]["title"] == "Firefox"
            
            # Check second window
            assert windows[1]["id"] == "9876543210"
            assert windows[1]["title"] == "Terminal"
        
        # Verify the correct command was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "gdbus" in call_args
        assert "org.gnome.Shell.Extensions.Windows.List" in call_args
    
    @patch('server.subprocess.run')
    async def test_list_windows_empty_result(self, mock_run, mcp_server):
        """Test handling of empty window list."""
        # Mock successful subprocess call with empty list
        mock_run.return_value = Mock(
            returncode=0,
            stdout="[]",
            stderr=""
        )
        
        async with Client(mcp_server) as client:
            result = await client.call_tool("list_windows", {})
            windows = json.loads(result.content[0].text)
            
            assert windows == []
    
    @patch('server.subprocess.run')
    async def test_list_windows_subprocess_error(self, mock_run, mcp_server):
        """Test handling of subprocess errors."""
        # Mock failed subprocess call
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error: Extension not found"
        )
        
        async with Client(mcp_server) as client:
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("list_windows", {})
            
            # Should contain error information
            assert "Failed to list windows" in str(exc_info.value)
    
    @patch('server.subprocess.run')
    async def test_list_windows_timeout(self, mock_run, mcp_server):
        """Test handling of subprocess timeout."""
        # Mock subprocess timeout
        mock_run.side_effect = subprocess.TimeoutExpired("gdbus", 10)
        
        async with Client(mcp_server) as client:
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("list_windows", {})
            
            assert "Timeout while listing windows" in str(exc_info.value)
    
    @patch('server.subprocess.run')
    async def test_list_windows_invalid_json(self, mock_run, mcp_server):
        """Test handling of invalid JSON response."""
        # Mock successful subprocess call with invalid JSON
        mock_run.return_value = Mock(
            returncode=0,
            stdout="invalid json",
            stderr=""
        )
        
        async with Client(mcp_server) as client:
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("list_windows", {})
            
            assert "Failed to parse window list JSON" in str(exc_info.value)
    
    @patch('server.subprocess.run')
    async def test_list_windows_missing_required_fields(self, mock_run, mcp_server):
        """Test handling of window data missing required fields."""
        # Mock data with missing 'id' field
        invalid_data = [
            {
                "wm_class": "Firefox",
                "frame_type": 0,
                "window_type": 0,
                # Missing 'id' field
            }
        ]
        
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(invalid_data),
            stderr=""
        )
        
        async with Client(mcp_server) as client:
            with pytest.raises(Exception):
                await client.call_tool("list_windows", {})
    
    def test_window_class_to_dict(self):
        """Test the Window class to_dict method."""
        from server import Window
        
        window = Window(id="123", title="Test Window")
        result = window.to_dict()
        
        assert result == {
            "id": "123",
            "title": "Test Window"
        }
    
    @patch('server.subprocess.run')
    async def test_list_windows_filters_correctly(self, mock_run, mcp_server):
        """Test that only normal windows are returned (frame_type=0, window_type=0)."""
        # Mock data with mixed window types
        mixed_data = [
            {
                "id": 1,
                "wm_class": "Normal Window",
                "frame_type": 0,
                "window_type": 0,
            },
            {
                "id": 2,
                "wm_class": "Dialog",
                "frame_type": 1,
                "window_type": 0,
            },
            {
                "id": 3,
                "wm_class": "Menu",
                "frame_type": 0,
                "window_type": 1,
            },
            {
                "id": 4,
                "wm_class": "Another Normal Window",
                "frame_type": 0,
                "window_type": 0,
            }
        ]
        
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(mixed_data),
            stderr=""
        )
        
        async with Client(mcp_server) as client:
            result = await client.call_tool("list_windows", {})
            windows = json.loads(result.content[0].text)
            
            # Should only return the 2 normal windows
            assert len(windows) == 2
            assert windows[0]["title"] == "Normal Window"
            assert windows[1]["title"] == "Another Normal Window"