"""Regressão de configuração do host.json — invariantes do queue worker.

O deadline cooperativo do worker (WORKER_DEADLINE_SECONDS) só funciona se:
  WORKER_DEADLINE_SECONDS < functionTimeout < visibilityTimeout
Também protege messageEncoding=none (extension bundle v4 default é Base64,
incompatível com o SDK Python) e maxDequeueCount=5 (poison queue semantics).
"""

import json
import os


def _load_host_json():
    path = os.path.join(os.path.dirname(__file__), "..", "host.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _hms_to_seconds(value: str) -> int:
    h, m, s = (int(p) for p in value.split(":"))
    return h * 3600 + m * 60 + s


class TestHostJsonQueueInvariants:
    def test_function_timeout_is_40_minutes(self):
        """(h) 25min de deadline + margem para consolidação/flush — 40min."""
        host = _load_host_json()
        assert host["functionTimeout"] == "00:40:00"

    def test_visibility_timeout_exceeds_function_timeout(self):
        """Mensagem só reaparece DEPOIS do worker morrer — nunca em paralelo."""
        host = _load_host_json()
        function_timeout = _hms_to_seconds(host["functionTimeout"])
        visibility = _hms_to_seconds(host["extensions"]["queues"]["visibilityTimeout"])
        assert visibility > function_timeout

    def test_worker_deadline_below_function_timeout(self):
        """Deadline cooperativo precisa disparar ANTES do functionTimeout."""
        from src.worker_helpers import WORKER_DEADLINE_SECONDS

        host = _load_host_json()
        function_timeout = _hms_to_seconds(host["functionTimeout"])
        assert WORKER_DEADLINE_SECONDS < function_timeout

    def test_message_encoding_none_preserved(self):
        """Obrigatório: bundle v4 default é Base64, incompatível com SDK Python."""
        host = _load_host_json()
        assert host["extensions"]["queues"]["messageEncoding"] == "none"

    def test_max_dequeue_count_preserved(self):
        """Poison queue semantics: 5 tentativas para crash loops genuínos."""
        host = _load_host_json()
        assert host["extensions"]["queues"]["maxDequeueCount"] == 5
