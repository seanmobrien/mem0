"""Telemetry helpers for Azure Application Insights instrumentation."""

from __future__ import annotations

import logging
import os
import socket
from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import Tracer
from opentelemetry.sdk.resources import Resource

_logger = logging.getLogger(__name__)
_configured = False


DISABLED_INSTRUMENTATIONS = {
    # azure-monitor-opentelemetry 1.5.0 conflicts with pkg_resources entry point dist() calls
    # under Python 3.12; disable auto-instrumentation for now and rely on explicit spans.
    name: {"enabled": False}
    for name in (
        "fastapi",
        "flask",
        "psycopg2",
        "requests",
        "urllib",
        "urllib3",
    )
}


def init_telemetry(connection_string: str, sampling_ratio: Optional[float] = None) -> Optional[Tracer]:
    """Configure Azure Monitor OpenTelemetry exporters and return a tracer.

    The azure-monitor-opentelemetry package wires FastAPI/ASGI, requests, logging,
    and database instrumentation automatically when configured. The returned
    tracer can be used to create custom spans within the application.
    """
    global _configured

    if not connection_string:
        return None

    if _configured:
        return trace.get_tracer(__name__)

    instance_id = os.getenv("HOSTNAME") or socket.gethostname()
    resource = Resource.create(
        {
            "service.name": "Mem0-Api",
            "service.instance.id": f"ObApps.ComplianceTheatre.Mem0-Api.{instance_id}",
            "service.namespace": "ObApps.ComplianceTheatre",
            "ai.cloud.roleBaseName": "mem0-api.jollybush-836e15bc.westus3.azurecontainerapps.io",
        }
    )

    class _DowngradeExceptionFilter(logging.Filter):
        _EXPECTED_ERROR_FRAGMENT = "'DistInfoDistribution' object is not callable"

        def filter(self, record: logging.LogRecord) -> bool:
            if not (record.levelno >= logging.ERROR and record.exc_info):
                return True

            _, exc_value, _ = record.exc_info
            if isinstance(exc_value, TypeError) and self._EXPECTED_ERROR_FRAGMENT in str(exc_value):
                record.levelno = logging.DEBUG
                record.levelname = "DEBUG"
            return True

    try:
        # Import inside runtime so a missing pkg_resources won't break module import
        from azure.monitor.opentelemetry import configure_azure_monitor

        logger = logging.getLogger("azure.monitor.opentelemetry._configure")
        logger.addFilter(_DowngradeExceptionFilter())
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).warning("Azure telemetry package not available: %s", exc)
        return trace.get_tracer(__name__)

    class _SuppressTransmissionLogs(logging.Filter):
        _MESSAGE_PREFIX = "Transmission succeeded:"

        def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
            return not record.getMessage().startswith(self._MESSAGE_PREFIX)

    logging.getLogger("azure.monitor.opentelemetry.exporter.export._base").addFilter(
        _SuppressTransmissionLogs()
    )

    configure_azure_monitor(
        connection_string=connection_string,
        sampling_ratio=sampling_ratio,
        instrumentation_options=DISABLED_INSTRUMENTATIONS,
        resource=resource,
    )
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    _configured = True

    _logger.info("Azure Monitor telemetry configured")
    return trace.get_tracer(__name__)
