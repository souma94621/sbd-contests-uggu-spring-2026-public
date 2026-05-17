"""Общие фикстуры для корневых тестов (сквозные сценарии ЦР → АБУ)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

# До любого monkeypatch на httpx.AsyncClient (иначе рекурсия).
_HttpxAsyncClient = httpx.AsyncClient


@pytest.fixture()
def dm_client_e2e(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """ЦР с маршрутизацией POST миссии на тестовое приложение АБУ (ASGI)."""
    monkeypatch.setenv("CR_CERT_POLICY", "permissive")

    from abu.app import app as abu_app
    from digital_mine import main as dm

    transport = httpx.ASGITransport(app=abu_app)

    class RoutedAsyncClient:
        def __init__(self, *a, **kw):
            self._timeout = kw.get("timeout", 15.0)

        async def __aenter__(self):
            self._inner = _HttpxAsyncClient(
                transport=transport,
                base_url="http://abu.test",
                timeout=float(self._timeout),
            )
            await self._inner.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self._inner.__aexit__(*args)

        async def post(self, url: str, **kwargs):
            from urllib.parse import urlparse

            path = urlparse(url).path or "/"
            return await self._inner.post(path, **kwargs)

        async def get(self, url: str, **kwargs):
            from urllib.parse import urlparse

            path = urlparse(url).path or "/"
            return await self._inner.get(path, **kwargs)

    monkeypatch.setattr(dm.httpx, "AsyncClient", RoutedAsyncClient)
    return TestClient(dm.app)
