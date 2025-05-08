from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test")

@mcp.tool(description="테스트 툴")
async def test_tool() -> str:
    return "test"

if __name__ == "__main__":
    mcp.run()
