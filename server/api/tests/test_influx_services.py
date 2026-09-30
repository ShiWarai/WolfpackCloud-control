"""Unit-тесты InfluxDB сервисов."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.schemas import RosOutIngestItem
from app.services import deployment_events_store, influx as influx_svc, ros_logs_store
from app.services.influx import InfluxError


@pytest.fixture
def influx_settings() -> Settings:
    return Settings(
        influxdb_url="http://influx.test:8086",
        influxdb_token="test-token",
        influxdb_org="wolfpackcloud_influxdb",
    )


def test_parse_flux_csv_extracts_data_rows():
    raw = """#datatype,string,long,dateTime:RFC3339,dateTime:RFC3339,dateTime:RFC3339,double,string,string,string,string,string,string,string
#group,false,false,true,true,false,false,true,true,true,true,true,true,true
#default,_result,,,,,,,,,,,,
,result,table,_start,_stop,_time,_value,_field,_measurement,deployment,from_host,status,to_host
,,0,2026-05-01T00:00:00Z,2026-05-22T00:00:00Z,2026-05-22T10:00:00Z,42,user_id,deployment_event,dep-a,w1,success,w2
"""
    rows = influx_svc._parse_flux_csv(raw)
    assert len(rows) == 1
    assert rows[0]["deployment"] == "dep-a"
    assert rows[0]["status"] == "success"


@pytest.mark.asyncio
async def test_write_ros_logs_calls_influx(influx_settings: Settings):
    items = [
        RosOutIngestItem(network_id=1, ros_node_name="/talker", level="INFO", message="hello")
    ]
    with patch("app.services.influx.write_lines", new_callable=AsyncMock) as mock_write:
        await ros_logs_store.write_ros_logs(influx_settings, items)
    mock_write.assert_awaited_once()
    assert "ros_log" in mock_write.await_args.args[2]


@pytest.mark.asyncio
async def test_list_ros_logs_maps_response(influx_settings: Settings):
    fake_rows = [
        {
            "result": "result",
            "_time": "2026-05-22T10:00:00Z",
            "_value": "msg",
            "network_id": "1",
            "node_name": "/n",
            "level": "WARN",
        }
    ]
    with patch("app.services.influx.query_flux", new_callable=AsyncMock, return_value=fake_rows):
        rows = await ros_logs_store.list_ros_logs(influx_settings, network_id=1, limit=10)
    assert len(rows) == 1
    assert rows[0]["message"] == "msg"
    assert rows[0]["network_id"] == 1


@pytest.mark.asyncio
async def test_record_deployment_event_skips_when_not_configured():
    settings = Settings(influxdb_url="", influxdb_token="")
    with patch("app.services.influx.write_lines", new_callable=AsyncMock) as mock_write:
        await deployment_events_store.record_deployment_event(
            settings,
            deployment="dep",
            status="success",
        )
    mock_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_deployment_event_writes_line(influx_settings: Settings):
    with patch("app.services.influx.write_lines", new_callable=AsyncMock) as mock_write:
        await deployment_events_store.record_deployment_event(
            influx_settings,
            deployment="dep-a",
            status="success",
            from_host="w1",
            to_host="w2",
            user_id=7,
            preset_id="preset-1",
        )
    mock_write.assert_awaited_once()
    line = mock_write.await_args.args[2]
    assert "deployment_event" in line
    assert "dep-a" in line


@pytest.mark.asyncio
async def test_list_deployment_events_maps_and_skips_bad_rows(influx_settings: Settings):
    fake_rows = [
        {
            "_time": "2026-05-22T10:00:00Z",
            "deployment": "dep-a",
            "from_host": "none",
            "to_host": "w2",
            "status": "success",
            "user_id": "3",
            "preset_id": "",
        },
        {"_time": "bad"},
    ]
    with patch("app.services.influx.query_flux", new_callable=AsyncMock, return_value=fake_rows):
        rows = await deployment_events_store.list_deployment_events(
            influx_settings,
            deployment="dep-a",
            status="success",
            limit=10,
        )
    assert len(rows) == 1
    assert rows[0]["deployment"] == "dep-a"
    assert rows[0]["from_host"] is None
    assert rows[0]["user_id"] == 3


def test_escape_helpers():
    assert influx_svc._escape_tag("a b,c=d") == r"a\ b\,c\=d"
    assert influx_svc._escape_field_string('say "hi"') == r'say \"hi\"'


@pytest.mark.asyncio
async def test_write_lines_not_configured_raises():
    settings = Settings(influxdb_url="", influxdb_token="")
    with pytest.raises(InfluxError, match="не настроен"):
        await influx_svc.write_lines(settings, "bucket", "line")


@pytest.mark.asyncio
async def test_write_lines_empty_skips_http(influx_settings: Settings):
    with patch("app.services.influx.httpx.AsyncClient") as mock_client_cls:
        await influx_svc.write_lines(influx_settings, "bucket", "  \n  ")
    mock_client_cls.assert_not_called()


def _mock_httpx_client(*, get=None, post=None):
    client = AsyncMock()
    client.get = AsyncMock(return_value=get) if get is not None else AsyncMock()
    client.post = AsyncMock(return_value=post) if post is not None else AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client


@pytest.mark.asyncio
async def test_write_lines_success(influx_settings: Settings):
    response = MagicMock(status_code=204, text="")
    client = _mock_httpx_client(post=response)
    with patch("app.services.influx.httpx.AsyncClient", return_value=client):
        await influx_svc.write_lines(influx_settings, "ros_logs", "m v=1i 1")
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_lines_http_error(influx_settings: Settings):
    response = MagicMock(status_code=500, text="boom")
    client = _mock_httpx_client(post=response)
    with patch("app.services.influx.httpx.AsyncClient", return_value=client):
        with pytest.raises(InfluxError, match="HTTP 500"):
            await influx_svc.write_lines(influx_settings, "ros_logs", "m v=1i 1")


@pytest.mark.asyncio
async def test_write_lines_request_error(influx_settings: Settings):
    client = _mock_httpx_client()
    client.post.side_effect = httpx.RequestError("conn refused", request=MagicMock())
    with patch("app.services.influx.httpx.AsyncClient", return_value=client):
        with pytest.raises(InfluxError):
            await influx_svc.write_lines(influx_settings, "ros_logs", "m v=1i 1")


@pytest.mark.asyncio
async def test_query_flux_success(influx_settings: Settings):
    csv_body = """#datatype,string,long
,result,table,_time,_value,_field,_measurement
,,0,2026-05-22T10:00:00Z,42,user_id,deployment_event
"""
    response = MagicMock(status_code=200, text=csv_body)
    client = _mock_httpx_client(post=response)
    with patch("app.services.influx.httpx.AsyncClient", return_value=client):
        rows = await influx_svc.query_flux(influx_settings, "from(bucket: \"x\")")
    assert len(rows) == 1
    assert rows[0]["_value"] == "42"


@pytest.mark.asyncio
async def test_query_flux_http_error(influx_settings: Settings):
    response = MagicMock(status_code=503, text="unavailable")
    client = _mock_httpx_client(post=response)
    with patch("app.services.influx.httpx.AsyncClient", return_value=client):
        with pytest.raises(InfluxError, match="HTTP 503"):
            await influx_svc.query_flux(influx_settings, "flux")


@pytest.mark.asyncio
async def test_ping_variants(influx_settings: Settings):
    disabled = Settings(influxdb_url="", influxdb_token="")
    assert await influx_svc.ping(disabled) is False

    ok = MagicMock(status_code=200)
    client = _mock_httpx_client(get=ok)
    with patch("app.services.influx.httpx.AsyncClient", return_value=client):
        assert await influx_svc.ping(influx_settings) is True

    client.get.side_effect = httpx.RequestError("down", request=MagicMock())
    with patch("app.services.influx.httpx.AsyncClient", return_value=client):
        assert await influx_svc.ping(influx_settings) is False


@pytest.mark.asyncio
async def test_write_ros_logs_empty_items(influx_settings: Settings):
    with patch("app.services.influx.write_lines", new_callable=AsyncMock) as mock_write:
        await ros_logs_store.write_ros_logs(influx_settings, [])
    mock_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_ros_logs_skips_invalid_record(influx_settings: Settings):
    fake_rows = [
        {
            "_time": "2026-05-22T10:00:00Z",
            "_value": "ok",
            "network_id": "1",
            "node_name": "/n",
            "level": "INFO",
        },
        {"node_name": "/bad"},
    ]
    with patch("app.services.influx.query_flux", new_callable=AsyncMock, return_value=fake_rows):
        rows = await ros_logs_store.list_ros_logs(influx_settings, network_id=1, limit=5)
    assert len(rows) == 1
    assert rows[0]["message"] == "ok"
