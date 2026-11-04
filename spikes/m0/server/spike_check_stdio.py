import asyncio, os
from mcp import StdioServerParameters
from spike_check import run
here = os.path.dirname(os.path.abspath(__file__))
asyncio.run(run(StdioServerParameters(command="uv", args=["run", "--directory", here, "python", "-m", "toprope_spike.server", "toy.domain.yaml", "stdio"], cwd=here)))
