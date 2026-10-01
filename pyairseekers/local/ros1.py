"""Pure-Python ROS1 message parser and deserializer.

Replaces the rosbags dependency to avoid C-extension build requirements
(lz4) that fail in the Home Assistant OS container.
"""

from __future__ import annotations

from dataclasses import dataclass, make_dataclass
import re
import struct
from typing import Any

_PRIMITIVES: dict[str, tuple[str, int]] = {
    "bool": ("?", 1),
    "int8": ("b", 1),
    "uint8": ("B", 1),
    "int16": ("h", 2),
    "uint16": ("H", 2),
    "int32": ("i", 4),
    "uint32": ("I", 4),
    "int64": ("q", 8),
    "uint64": ("Q", 8),
    "float32": ("f", 4),
    "float64": ("d", 8),
    "byte": ("b", 1),
    "char": ("B", 1),
}


@dataclass(frozen=True)
class _FieldDef:
    """A single field in a ROS1 message definition."""

    name: str
    type_name: str
    is_array: bool = False
    array_size: int | None = None


@dataclass
class RosTime:
    """ROS1 time/duration: two uint32 fields."""

    secs: int = 0
    nsecs: int = 0


def to_type_path(name: str) -> str:
    """Turn a ROS1 schema name ``pkg/Type`` into a type path ``pkg/msg/Type``."""
    parts = name.split("/")
    return f"{parts[0]}/msg/{parts[1]}" if len(parts) == 2 else name


class Typestore:
    """Registry of ROS1 message types with binary deserialization."""

    def __init__(self) -> None:
        self._types: dict[str, list[_FieldDef]] = {}
        self._classes: dict[str, type] = {}

    def register(self, types: dict[str, list[_FieldDef]]) -> None:
        """Add or replace type definitions from ``parse_msg_text``."""
        for type_path, fields in types.items():
            self._types[type_path] = fields
            self._classes.pop(type_path, None)

    def deserialize_ros1(self, data: bytes, type_path: str) -> object:
        """Decode one ROS1-serialised message into a dataclass instance.

        Raises:
            KeyError: ``type_path`` (or a nested type) is not registered.
            struct.error: the payload is shorter than the type requires.
        """
        obj, _ = self._deserialize(data, 0, type_path)
        return obj

    def _get_class(self, type_path: str) -> type:
        if type_path not in self._classes:
            fields = self._types[type_path]
            name = type_path.rsplit("/", 1)[-1]
            dc_fields = [(f.name, Any) for f in fields]
            self._classes[type_path] = make_dataclass(name, dc_fields)
        return self._classes[type_path]

    def _resolve_type(self, type_ref: str, current_pkg: str) -> str:
        if "/" in type_ref:
            return to_type_path(type_ref)
        if type_ref == "Header":
            return "std_msgs/msg/Header"
        return f"{current_pkg}/msg/{type_ref}"

    def _deserialize(self, data: bytes, offset: int, type_path: str) -> tuple[Any, int]:
        fields = self._types.get(type_path)
        if fields is None:
            raise KeyError(f"Type {type_path} not registered")

        values: dict[str, Any] = {}
        for f in fields:
            if f.is_array:
                values[f.name], offset = self._read_array(data, offset, f, type_path)
            elif f.type_name in _PRIMITIVES:
                fmt, size = _PRIMITIVES[f.type_name]
                values[f.name] = struct.unpack_from(f"<{fmt}", data, offset)[0]
                offset += size
            elif f.type_name == "string":
                slen = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                values[f.name] = data[offset : offset + slen].decode("utf-8", errors="replace")
                offset += slen
            elif f.type_name in ("time", "duration"):
                secs = struct.unpack_from("<I", data, offset)[0]
                nsecs = struct.unpack_from("<I", data, offset + 4)[0]
                offset += 8
                values[f.name] = RosTime(secs=secs, nsecs=nsecs)
            else:
                pkg = type_path.split("/", maxsplit=1)[0]
                nested = self._resolve_type(f.type_name, pkg)
                values[f.name], offset = self._deserialize(data, offset, nested)

        cls = self._get_class(type_path)
        return cls(**values), offset

    def _read_array(
        self,
        data: bytes,
        offset: int,
        f: _FieldDef,
        parent_type: str,
    ) -> tuple[list[Any], int]:
        if f.array_size is not None:
            count = f.array_size
        else:
            count = struct.unpack_from("<I", data, offset)[0]
            offset += 4

        if f.type_name in _PRIMITIVES:
            fmt, size = _PRIMITIVES[f.type_name]
            if count == 0:
                return [], offset
            values = list(struct.unpack_from(f"<{count}{fmt}", data, offset))
            offset += size * count
            return values, offset

        if f.type_name == "string":
            arr: list[Any] = []
            for _ in range(count):
                slen = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                arr.append(data[offset : offset + slen].decode("utf-8", errors="replace"))
                offset += slen
            return arr, offset

        pkg = parent_type.split("/", maxsplit=1)[0]
        nested = self._resolve_type(f.type_name, pkg)
        arr = []
        for _ in range(count):
            obj, offset = self._deserialize(data, offset, nested)
            arr.append(obj)
        return arr, offset


def parse_msg_text(msg_text: str, schema_name: str) -> dict[str, list[_FieldDef]]:
    """Parse a ROS1 .msg definition (possibly multi-type) into field lists.

    Returns dict mapping type paths ("pkg/msg/Type") to their field definitions.
    The schema may contain multiple definitions separated by "===" lines
    with "MSG: pkg/Type" headers for nested types.
    """
    main_type_path = to_type_path(schema_name)

    blocks: list[tuple[str, list[str]]] = []
    current_path = main_type_path
    current_lines: list[str] = []

    for line in msg_text.splitlines():
        stripped = line.strip()
        if re.match(r"^={3,}$", stripped):
            blocks.append((current_path, current_lines))
            current_lines = []
            current_path = ""
            continue
        m = re.match(r"^MSG:\s*([\w/]+)\s*$", stripped)
        if m:
            current_path = to_type_path(m.group(1))
            continue
        current_lines.append(stripped)

    blocks.append((current_path, current_lines))

    result: dict[str, list[_FieldDef]] = {}
    for type_path, lines in blocks:
        if not type_path:
            continue
        fields = _parse_fields(lines)
        if fields:
            result[type_path] = fields

    return result


def _parse_fields(lines: list[str]) -> list[_FieldDef]:
    fields: list[_FieldDef] = []
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" in line:
            continue
        m = re.match(r"^([\w/]+)(\[(\d*)\])?\s+(\w+)$", line)
        if not m:
            continue
        type_name = m.group(1)
        bracket = m.group(2)
        size_str = m.group(3)
        name = m.group(4)
        fields.append(
            _FieldDef(
                name=name,
                type_name=type_name,
                is_array=bracket is not None,
                array_size=int(size_str) if size_str else None,
            )
        )
    return fields
