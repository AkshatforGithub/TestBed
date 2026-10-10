import json

from agents.common import harden


class FakeTool:
    description = "fake"
    args_schema = {
        "type": "object",
        "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}},
    }

    def __init__(self, name, outputs):
        self.name = name
        self.outputs = list(outputs)
        self.calls = []

    async def ainvoke(self, kwargs):
        self.calls.append(dict(kwargs))
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


async def test_retries_after_exception_and_garbage():
    fake = FakeTool("lookup_order", [RuntimeError("503"), "<<<garbled>>>", json.dumps({"ok": 1})])
    tool = harden(fake, retries=3, timeout=1, backoff=0)
    assert json.loads(await tool.ainvoke({"order_id": "A100"})) == {"ok": 1}
    assert len(fake.calls) == 3


async def test_gives_up_with_structured_error():
    fake = FakeTool("lookup_order", [RuntimeError("503")] * 3)
    tool = harden(fake, retries=3, timeout=1, backoff=0)
    assert "tool unavailable" in json.loads(await tool.ainvoke({"order_id": "A100"}))["error"]


async def test_refund_gets_idempotency_key():
    fake = FakeTool("issue_refund", [json.dumps({"status": "refunded"})])
    tool = harden(fake, retries=1, timeout=1, backoff=0)
    await tool.ainvoke({"order_id": "A100", "amount": 42.0})
    assert fake.calls[0]["idempotency_key"] == "A100:42.00"


async def test_business_error_is_not_retried():
    fake = FakeTool("lookup_order", [json.dumps({"error": "order not found"})])
    tool = harden(fake, retries=3, timeout=1, backoff=0)
    assert "order not found" in await tool.ainvoke({"order_id": "A999"})
    assert len(fake.calls) == 1
