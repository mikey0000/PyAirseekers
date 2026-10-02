"""Tests for the pure-Python ROS1 message parser and deserializer."""

from __future__ import annotations

import struct

import pytest

from pyairseekers.local.ros1 import (
    RosTime,
    Typestore,
    _FieldDef,
    encode_string,
    parse_msg_text,
    schema_fields,
)

# ---------------------------------------------------------------------------
# parse_msg_text
# ---------------------------------------------------------------------------


class TestParseMsgText:
    """Test the .msg definition parser."""

    def test_simple_single_type(self) -> None:
        schema = "float64 x\nfloat64 y\nfloat64 z\n"
        result = parse_msg_text(schema, "geometry_msgs/Point")
        assert "geometry_msgs/msg/Point" in result
        fields = result["geometry_msgs/msg/Point"]
        assert len(fields) == 3
        assert fields[0] == _FieldDef(name="x", type_name="float64")
        assert fields[1] == _FieldDef(name="y", type_name="float64")
        assert fields[2] == _FieldDef(name="z", type_name="float64")

    def test_constants_are_skipped(self) -> None:
        schema = "uint8 POWER_SUPPLY_STATUS_UNKNOWN=0\nuint8 POWER_SUPPLY_STATUS_CHARGING=1\nfloat32 voltage\n"
        result = parse_msg_text(schema, "sensor_msgs/BatteryState")
        fields = result["sensor_msgs/msg/BatteryState"]
        assert len(fields) == 1
        assert fields[0].name == "voltage"

    def test_comments_are_stripped(self) -> None:
        schema = "float32 voltage  # Battery voltage in Volts\nfloat32 current  # Negative when discharging\n"
        result = parse_msg_text(schema, "sensor_msgs/BatteryState")
        fields = result["sensor_msgs/msg/BatteryState"]
        assert len(fields) == 2
        assert fields[0].name == "voltage"
        assert fields[1].name == "current"

    def test_multi_block_schema(self) -> None:
        schema = (
            "Header header\n"
            "NavSatStatus status\n"
            "float64 latitude\n"
            "float64 longitude\n"
            "float64 altitude\n"
            "===\n"
            "MSG: std_msgs/Header\n"
            "uint32 seq\n"
            "time stamp\n"
            "string frame_id\n"
            "===\n"
            "MSG: sensor_msgs/NavSatStatus\n"
            "int8 status\n"
            "uint16 service\n"
        )
        result = parse_msg_text(schema, "sensor_msgs/NavSatFix")
        assert "sensor_msgs/msg/NavSatFix" in result
        assert "std_msgs/msg/Header" in result
        assert "sensor_msgs/msg/NavSatStatus" in result

        main = result["sensor_msgs/msg/NavSatFix"]
        assert main[0].name == "header"
        assert main[1].name == "status"
        assert main[2].name == "latitude"

        header = result["std_msgs/msg/Header"]
        assert len(header) == 3
        assert header[1].type_name == "time"

    def test_variable_length_array(self) -> None:
        schema = "uint8[] data\n"
        result = parse_msg_text(schema, "std_msgs/UInt8MultiArray")
        fields = result["std_msgs/msg/UInt8MultiArray"]
        assert fields[0].is_array is True
        assert fields[0].array_size is None

    def test_fixed_length_array(self) -> None:
        schema = "float64[36] position_covariance\n"
        result = parse_msg_text(schema, "sensor_msgs/NavSatFix")
        fields = result["sensor_msgs/msg/NavSatFix"]
        assert fields[0].is_array is True
        assert fields[0].array_size == 36

    def test_empty_lines_ignored(self) -> None:
        schema = "\nfloat32 data\n\n"
        result = parse_msg_text(schema, "std_msgs/Float32")
        fields = result["std_msgs/msg/Float32"]
        assert len(fields) == 1


# ---------------------------------------------------------------------------
# Typestore deserialization
# ---------------------------------------------------------------------------


def _build_store_with_type(type_path: str, fields: list[_FieldDef]) -> Typestore:
    store = Typestore()
    store.register({type_path: fields})
    return store


class TestTypestore:
    """Test binary ROS1 deserialization."""

    def test_primitives(self) -> None:
        fields = [
            _FieldDef(name="a", type_name="int32"),
            _FieldDef(name="b", type_name="float64"),
            _FieldDef(name="c", type_name="bool"),
        ]
        store = _build_store_with_type("test/msg/Msg", fields)
        data = struct.pack("<id?", 42, 3.14, True)
        result = store.deserialize_ros1(data, "test/msg/Msg")
        assert result.a == 42
        assert abs(result.b - 3.14) < 1e-10
        assert result.c is True

    def test_string(self) -> None:
        fields = [_FieldDef(name="data", type_name="string")]
        store = _build_store_with_type("std_msgs/msg/String", fields)
        payload = b"hello"
        data = struct.pack("<I", len(payload)) + payload
        result = store.deserialize_ros1(data, "std_msgs/msg/String")
        assert result.data == "hello"

    def test_nested_type(self) -> None:
        inner_fields = [_FieldDef(name="status", type_name="int8")]
        outer_fields = [
            _FieldDef(name="latitude", type_name="float64"),
            _FieldDef(name="status", type_name="sensor_msgs/NavSatStatus"),
        ]
        store = Typestore()
        store.register(
            {
                "sensor_msgs/msg/NavSatStatus": inner_fields,
                "sensor_msgs/msg/NavSatFix": outer_fields,
            }
        )
        data = struct.pack("<db", 51.5074, -1)
        result = store.deserialize_ros1(data, "sensor_msgs/msg/NavSatFix")
        assert abs(result.latitude - 51.5074) < 1e-4
        assert result.status.status == -1

    def test_time_field(self) -> None:
        fields = [_FieldDef(name="stamp", type_name="time")]
        store = _build_store_with_type("test/msg/T", fields)
        data = struct.pack("<II", 1000, 500000)
        result = store.deserialize_ros1(data, "test/msg/T")
        assert isinstance(result.stamp, RosTime)
        assert result.stamp.secs == 1000
        assert result.stamp.nsecs == 500000

    def test_duration_field(self) -> None:
        fields = [_FieldDef(name="dur", type_name="duration")]
        store = _build_store_with_type("test/msg/D", fields)
        data = struct.pack("<II", 60, 0)
        result = store.deserialize_ros1(data, "test/msg/D")
        assert isinstance(result.dur, RosTime)
        assert result.dur.secs == 60

    def test_variable_length_array(self) -> None:
        fields = [_FieldDef(name="data", type_name="int32", is_array=True, array_size=None)]
        store = _build_store_with_type("test/msg/A", fields)
        data = struct.pack("<I3i", 3, 10, 20, 30)
        result = store.deserialize_ros1(data, "test/msg/A")
        assert result.data == [10, 20, 30]

    def test_fixed_length_array(self) -> None:
        fields = [_FieldDef(name="rgb", type_name="uint8", is_array=True, array_size=3)]
        store = _build_store_with_type("test/msg/C", fields)
        data = struct.pack("<3B", 255, 128, 0)
        result = store.deserialize_ros1(data, "test/msg/C")
        assert result.rgb == [255, 128, 0]

    def test_empty_variable_array(self) -> None:
        fields = [_FieldDef(name="items", type_name="float32", is_array=True, array_size=None)]
        store = _build_store_with_type("test/msg/E", fields)
        data = struct.pack("<I", 0)
        result = store.deserialize_ros1(data, "test/msg/E")
        assert result.items == []

    def test_string_array(self) -> None:
        fields = [_FieldDef(name="names", type_name="string", is_array=True, array_size=None)]
        store = _build_store_with_type("test/msg/SA", fields)
        s1 = b"foo"
        s2 = b"bar"
        data = struct.pack("<I", 2) + struct.pack("<I", 3) + s1 + struct.pack("<I", 3) + s2
        result = store.deserialize_ros1(data, "test/msg/SA")
        assert result.names == ["foo", "bar"]

    def test_byte_is_signed_int8(self) -> None:
        fields = [_FieldDef(name="val", type_name="byte")]
        store = _build_store_with_type("test/msg/B", fields)
        data = struct.pack("<b", -1)
        result = store.deserialize_ros1(data, "test/msg/B")
        assert result.val == -1

    def test_char_is_unsigned_uint8(self) -> None:
        fields = [_FieldDef(name="val", type_name="char")]
        store = _build_store_with_type("test/msg/CH", fields)
        data = struct.pack("<B", 200)
        result = store.deserialize_ros1(data, "test/msg/CH")
        assert result.val == 200

    def test_unregistered_type_raises(self) -> None:
        store = Typestore()
        with pytest.raises(KeyError, match="not registered"):
            store.deserialize_ros1(b"\x00", "unknown/msg/Type")

    def test_uint64_field(self) -> None:
        fields = [_FieldDef(name="data", type_name="uint64")]
        store = _build_store_with_type("std_msgs/msg/UInt64", fields)
        data = struct.pack("<Q", 0xDEADBEEF)
        result = store.deserialize_ros1(data, "std_msgs/msg/UInt64")
        assert result.data == 0xDEADBEEF

    def test_header_shorthand_resolves(self) -> None:
        """'Header' without a package prefix resolves to std_msgs/msg/Header."""
        header_fields = [
            _FieldDef(name="seq", type_name="uint32"),
            _FieldDef(name="stamp", type_name="time"),
            _FieldDef(name="frame_id", type_name="string"),
        ]
        msg_fields = [
            _FieldDef(name="header", type_name="Header"),
            _FieldDef(name="data", type_name="float32"),
        ]
        store = Typestore()
        store.register(
            {
                "std_msgs/msg/Header": header_fields,
                "test/msg/WithHeader": msg_fields,
            }
        )
        frame_id = b"base_link"
        data = (
            struct.pack("<I", 1)
            + struct.pack("<II", 100, 200)
            + struct.pack("<I", len(frame_id))
            + frame_id
            + struct.pack("<f", 1.5)
        )
        result = store.deserialize_ros1(data, "test/msg/WithHeader")
        assert result.header.seq == 1
        assert result.header.frame_id == "base_link"
        assert abs(result.data - 1.5) < 1e-6

    def test_roundtrip_parse_and_deserialize(self) -> None:
        """End-to-end: parse a .msg schema and deserialize matching bytes."""
        schema = "float32 percentage\nfloat32 voltage\nfloat32 current\nfloat32 temperature\n"
        types = parse_msg_text(schema, "sensor_msgs/BatteryState")
        store = Typestore()
        store.register(types)
        data = struct.pack("<ffff", 0.85, 25.2, -1.5, 35.0)
        msg = store.deserialize_ros1(data, "sensor_msgs/msg/BatteryState")
        assert abs(msg.percentage - 0.85) < 1e-5
        assert abs(msg.voltage - 25.2) < 0.1
        assert abs(msg.current - (-1.5)) < 1e-5
        assert abs(msg.temperature - 35.0) < 0.1


class TestEncodeString:
    def test_is_length_prefixed_utf8(self) -> None:
        assert encode_string("stop") == b"\x04\x00\x00\x00stop"

    def test_length_counts_bytes_not_characters(self) -> None:
        assert encode_string("é") == b"\x02\x00\x00\x00\xc3\xa9"


class TestSchemaFields:
    def test_ignores_comments_blank_lines_and_spacing(self) -> None:
        assert schema_fields("# header\nstring   arg  # stop/pause\n\nint32 result\n") == ["string arg", "int32 result"]

    def test_comment_only_schema_has_no_fields(self) -> None:
        assert schema_fields("# nothing here\n\n") == []
