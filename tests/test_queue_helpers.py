"""Tests for queue_helpers — enqueue_job."""

import json
import os
import sys
import importlib
from unittest.mock import patch, MagicMock


def _reload_enqueue():
    """Force reimport of enqueue_job to pick up patched environment."""
    if "src.queue_helpers" in sys.modules:
        importlib.reload(sys.modules["src.queue_helpers"])
    from src.queue_helpers import enqueue_job

    return enqueue_job


class TestEnqueueJob:
    """enqueue_job deve enviar mensagem para a queue taxonomy-jobs."""

    def test_enqueue_calls_send_message(self):
        """Verifica que o payload correto é enviado."""
        mock_queue_client = MagicMock()
        mock_queue_class = MagicMock()
        mock_queue_class.from_connection_string.return_value = mock_queue_client

        # Mock the azure.storage.queue module before importing enqueue_job
        mock_module = MagicMock()
        mock_module.QueueClient = mock_queue_class

        with patch.dict(
            os.environ,
            {"AzureWebJobsStorage": "DefaultEndpointsProtocol=https;AccountName=test"},
        ):
            with patch.dict(sys.modules, {"azure.storage.queue": mock_module}):
                enqueue_job = _reload_enqueue()
                enqueue_job("test-job-123")

                mock_queue_class.from_connection_string.assert_called_once()
                mock_queue_client.create_queue.assert_called_once()
                mock_queue_client.send_message.assert_called_once()

                sent_msg = mock_queue_client.send_message.call_args[0][0]
                payload = json.loads(sent_msg)
                assert payload == {"job_id": "test-job-123"}

    def test_handles_missing_connection_string(self, caplog):
        """Sem AzureWebJobsStorage → loga error sem exceção."""
        mock_module = MagicMock()

        env = {k: v for k, v in os.environ.items() if k != "AzureWebJobsStorage"}
        with patch.dict(os.environ, env, clear=True):
            with patch.dict(sys.modules, {"azure.storage.queue": mock_module}):
                enqueue_job = _reload_enqueue()
                enqueue_job("test-job-456")  # não deve levantar exceção

        assert any("AzureWebJobsStorage" in r.message for r in caplog.records)

    def test_handles_send_failure(self, caplog):
        """Erro no envio → loga error sem exceção."""
        mock_queue_client = MagicMock()
        mock_queue_client.send_message.side_effect = Exception("Connection refused")
        mock_queue_class = MagicMock()
        mock_queue_class.from_connection_string.return_value = mock_queue_client

        mock_module = MagicMock()
        mock_module.QueueClient = mock_queue_class

        with patch.dict(
            os.environ,
            {"AzureWebJobsStorage": "DefaultEndpointsProtocol=https;AccountName=test"},
        ):
            with patch.dict(sys.modules, {"azure.storage.queue": mock_module}):
                enqueue_job = _reload_enqueue()
                enqueue_job("test-job-789")  # não deve levantar exceção

        assert any("Falha ao enfileirar" in r.message for r in caplog.records)


class TestEnqueueJobReturnValue:
    """enqueue_job deve retornar bool indicando sucesso."""

    def test_returns_false_when_no_connection_string(self):
        """Sem AzureWebJobsStorage, deve retornar False."""
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}):
            enqueue_job = _reload_enqueue()
            result = enqueue_job("test-job-id")
        assert result is False

    def test_returns_true_on_success(self):
        """Com conexão válida e envio ok, deve retornar True."""
        mock_queue_client = MagicMock()
        mock_queue_class = MagicMock()
        mock_queue_class.from_connection_string.return_value = mock_queue_client
        mock_module = MagicMock()
        mock_module.QueueClient = mock_queue_class

        with patch.dict(os.environ, {"AzureWebJobsStorage": "DefaultEndpoints..."}):
            with patch.dict(sys.modules, {"azure.storage.queue": mock_module}):
                enqueue_job = _reload_enqueue()
                result = enqueue_job("test-job-id")
        assert result is True

    def test_returns_false_on_send_error(self):
        """Se send_message falha, deve retornar False."""
        mock_queue_client = MagicMock()
        mock_queue_client.send_message.side_effect = Exception("Connection refused")
        mock_queue_class = MagicMock()
        mock_queue_class.from_connection_string.return_value = mock_queue_client
        mock_module = MagicMock()
        mock_module.QueueClient = mock_queue_class

        with patch.dict(os.environ, {"AzureWebJobsStorage": "DefaultEndpoints..."}):
            with patch.dict(sys.modules, {"azure.storage.queue": mock_module}):
                enqueue_job = _reload_enqueue()
                result = enqueue_job("test-job-id")
        assert result is False
