def test_mcp_server_importable() -> None:
    import mcp_server

    assert mcp_server.__doc__ is None or isinstance(mcp_server.__doc__, str)
