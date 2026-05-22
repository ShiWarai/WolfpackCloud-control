"""Unit-тесты InfluxDB сервисов."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.schemas import RosOutIngestItem
from app.services import deployment_events_store, influx as influx_svc, ros_logs_store


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
