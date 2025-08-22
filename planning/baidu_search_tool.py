import asyncio
from appbuilder.mcp_server.client import MCPClient


async def main():
    client = MCPClient()
    await client.connect_to_server(service_url=service_url)
    print(client.tools)
    result = await client.call_tool("AIsearch", {"query": "王者荣耀最强", "model": "ernie-3.5-8k"})
    print(result)

if __name__ == "__main__":
    service_url = (
        "http://appbuilder.baidu.com/v2/ai_search/mcp/sse?api_key=bce-v3/ALTAK-Yn3DHHsswoXY17YawiLA9/10a53602a125cff122d8859dc73b4c2cbe5cc4fa"
    )
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())