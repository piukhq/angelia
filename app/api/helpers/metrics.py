"""
    Helper functions for generating metrics
"""
import socket
from functools import partial
from time import perf_counter_ns

import falcon

from app.report import api_logger
from settings import METRICS_PORT, METRICS_SIDECAR_DOMAIN, PERFORMANCE_METRICS


def _metrics_logger(msg: str) -> None:
    api_logger.debug(f"[Hermes Api2] {msg}")


def get_latency_metric(req: falcon.Request, req_end_time: float) -> float | None:
    try:
        return req_end_time - req.context.start_time
    except AttributeError as err:
        _metrics_logger(str(err))

    return None


def get_perf_latency_metric(req: falcon.Request) -> float | None:
    try:
        return round((perf_counter_ns() - req.context.start_perf) / 1000000, 1)
    except AttributeError as err:
        _metrics_logger(str(err))

    return None


def starter_timer(req: falcon.Request, now: float) -> None:
    req.context.start_perf = perf_counter_ns()
    req.context.start_time = now


def _create_udp_packet(api_name: str, kwargs: dict) -> bytes:
    packet_data = {
        "api_name": api_name,
        "status": kwargs.get("status"),
        "request_latency_ms": kwargs.get("performance_latency"),
        "request_latency": kwargs.get("request_latency"),
        "time_code": kwargs.get("time_code"),
        "end_point": kwargs.get("end_point"),
    }
    return str.encode(str(packet_data))


def _send_udp_packet(
    host: int | str,
    port: int,
    packet_data: bytes,
) -> None:
    if PERFORMANCE_METRICS:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        try:
            s.connect((host, port))
            num_of_bytes_sent = s.send(packet_data)
            s.close()
            _metrics_logger(f"number of bytes sent: {num_of_bytes_sent}")
        except ConnectionRefusedError as err:
            _metrics_logger(str(err))


stream_metrics = partial(_send_udp_packet, METRICS_SIDECAR_DOMAIN, METRICS_PORT)
get_metrics_as_bytes = partial(_create_udp_packet, "hermes_api2")
