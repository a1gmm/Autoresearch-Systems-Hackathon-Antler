from research_core.raindrop import workshop


def test_workshop_noop_without_endpoint():
    tracer = workshop(None)
    tracer.event("run_1", "scope", {"ok": True})
    tracer.finish("run_1")


def test_workshop_swallows_endpoint_errors():
    calls = []

    def failing_sender(endpoint, event):
        calls.append((endpoint, event))
        raise RuntimeError("network unavailable")

    tracer = workshop("https://trace.example.test", sender=failing_sender)
    tracer.event("run_1", "scope", {"ok": True})
    tracer.finish("run_1")

    assert len(calls) == 2
    assert tracer.failures
    assert tracer.failures[0]["error_type"] == "RuntimeError"
