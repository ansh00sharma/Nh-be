from threading import Lock


_lock = Lock()
_metrics = {
    "total_requests": 0,
    "successful_requests": 0,
    "error_requests": 0,
}


def record_request(status_code):
    with _lock:
        _metrics["total_requests"] += 1
        if status_code < 400:
            _metrics["successful_requests"] += 1
        else:
            _metrics["error_requests"] += 1


def get_metrics():
    with _lock:
        return dict(_metrics)


def reset_metrics():
    with _lock:
        for key in _metrics:
            _metrics[key] = 0
