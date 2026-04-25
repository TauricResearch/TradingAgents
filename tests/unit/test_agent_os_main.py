import urllib.error

from agent_os.backend import main


class _FakeResponse:
    def __init__(self, body: str):
        self._body = body

    def read(self):
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_agent_os_already_running_returns_true_for_agent_health(monkeypatch):
    captured = {}

    def _urlopen(url, timeout=1.0):
        captured["timeout"] = timeout
        return _FakeResponse('{"status":"ok","service":"AgentOS API"}')

    monkeypatch.setenv("AGENT_OS_HEALTHCHECK_TIMEOUT_SEC", "2.5")
    monkeypatch.setattr(
        main.urllib.request,
        "urlopen",
        _urlopen,
    )

    assert main._agent_os_already_running("0.0.0.0", 8088) is True
    assert captured["timeout"] == 2.5


def test_agent_os_already_running_returns_false_on_non_agent_response(monkeypatch):
    monkeypatch.setattr(
        main.urllib.request,
        "urlopen",
        lambda url, timeout=1.0: _FakeResponse('{"status":"ok","service":"Other API"}'),
    )

    assert main._agent_os_already_running("0.0.0.0", 8088) is False


def test_agent_os_already_running_returns_false_on_url_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(main.urllib.request, "urlopen", _raise)

    assert main._agent_os_already_running("0.0.0.0", 8088) is False


class _FakeSocket:
    def __init__(self, result: int):
        self._result = result
        self.timeout = None

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect_ex(self, addr):
        return self._result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_port_is_bound_returns_true_when_connect_ex_succeeds(monkeypatch):
    monkeypatch.setattr(main.socket, "socket", lambda *args, **kwargs: _FakeSocket(0))

    assert main._port_is_bound("127.0.0.1", 8088) is True


def test_port_is_bound_returns_false_when_connect_ex_fails(monkeypatch):
    monkeypatch.setattr(main.socket, "socket", lambda *args, **kwargs: _FakeSocket(1))

    assert main._port_is_bound("127.0.0.1", 8088) is False
