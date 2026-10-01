from __future__ import annotations

from pyairseekers.models import IoTCert, LiveStream


class TestRedaction:
    def test_iot_cert_repr_hides_keys(self) -> None:
        cert = IoTCert(ca="ca", cert_key="ck-secret", mqtt_broker="b:1", mqtt_client_id="id", private_key="pk-secret")

        assert "ck-secret" not in repr(cert)
        assert "pk-secret" not in repr(cert)

    def test_live_stream_repr_hides_sdp_and_resource(self) -> None:
        stream = LiveStream(answer_sdp="a=ice-pwd:secret", resource_url="http://srs.invalid/session/abc")

        assert "ice-pwd" not in repr(stream)
        assert "session/abc" not in repr(stream)
