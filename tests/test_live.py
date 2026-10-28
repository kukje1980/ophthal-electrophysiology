"""Live WebSocket stream: meta, data with triggers, impedance."""


def test_live_stream_sends_meta_and_data(client):
    with client.websocket_connect("/ws/live") as ws:
        meta = ws.receive_json()
        assert meta["type"] == "meta" and meta["fs"] > 0
        kinds = set()
        for _ in range(40):
            m = ws.receive_json()
            kinds.add(m["type"])
            if {"data", "imp"} <= kinds:
                break
        assert "data" in kinds


def test_live_stream_reports_bad_driver(client):
    with client.websocket_connect("/ws/live?driver=nope") as ws:
        m = ws.receive_json()
        assert m["type"] == "error" and m["phase"] == "open"
