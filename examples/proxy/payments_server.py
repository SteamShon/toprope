"""A stand-in for a team's existing payments MCP server: it refunds whatever it is asked to.
The rules about refunds are not here; `toprope-proxy` puts them in front of it."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

ORDERS = {"O-3": {"total": 80.0}, "O-8": {"total": 120.0}}
REFUNDS: list[dict] = []


def build() -> MCPServer:
    server = MCPServer(name="payments")

    @server.tool(description="Refund an order. The payment provider refuses more than the order's total.")
    def refund_order(order_id: str, amount: float) -> dict:
        order = ORDERS.get(order_id)
        if order is None or amount > order["total"]:
            raise ToolError(f"the provider refused: {amount} is more than {order_id}'s total")
        REFUNDS.append({"order_id": order_id, "amount": amount})
        return {"refund_id": f"R-{len(REFUNDS)}", "amount": amount}

    @server.tool(description="Read an order.", annotations={"readOnlyHint": True})
    def get_order(order_id: str) -> dict:
        return {"order_id": order_id, **ORDERS.get(order_id, {})}

    @server.tool(description="Delete every order. Nothing binds this, so the proxy never offers it.")
    def wipe_orders() -> dict:
        ORDERS.clear()
        return {"ok": True}

    return server


if __name__ == "__main__":
    build().run("stdio")
