import asyncio
from esql_handler_agent.agents.agent import root_agent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.invocation_context import InvocationContext

async def run_agent():
    invocation_context = InvocationContext(tool_name="esql-handler-agent")
    context = ToolContext(invocation_context=invocation_context)
    result = await root_agent.run(context)
    print(result)

if __name__ == "__main__":
    asyncio.run(run_agent())
