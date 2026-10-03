"""
bot/mod/ai/json_values.py

Modification():

- 驗證並複製嚴格 JSON Value。
- 禁止 Tuple、非字串 Object Key、NaN 與 Infinity 被靜默轉型。

本檔提供 AI Module Domain Models 共用的 JSON 邊界。
"""

from __future__ import annotations

import json
import math
from typing import TypeAlias, cast


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def normalize_json_value(
    value: object,
    *,
    field_name: str,
    max_bytes: int | None = None,
) -> JsonValue:
    """回傳與輸入分離、型別不會在 JSON Round-trip 改變的值。"""

    normalized = _normalize(
        value,
        field_name=field_name,
    )
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    if max_bytes is not None and len(encoded) > max_bytes:
        raise ValueError(
            f"{field_name} 不得超過 {max_bytes} UTF-8 bytes"
        )

    return normalized


def dump_json_value(
    value: object,
    *,
    field_name: str,
    max_bytes: int | None = None,
) -> str:
    normalized = normalize_json_value(
        value,
        field_name=field_name,
        max_bytes=max_bytes,
    )
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _normalize(
    value: object,
    *,
    field_name: str,
) -> JsonValue:
    if value is None or type(value) in {str, int, bool}:
        return cast(JsonScalar, value)

    if type(value) is float:
        number = cast(float, value)
        if not math.isfinite(number):
            raise ValueError(
                f"{field_name} 不得包含 NaN 或 Infinity"
            )
        return number

    if type(value) is list:
        return [
            _normalize(item, field_name=field_name)
            for item in cast(list[object], value)
        ]

    if type(value) is dict:
        source = cast(dict[object, object], value)
        normalized_object: dict[str, JsonValue] = {}
        for key, item in source.items():
            if type(key) is not str:
                raise ValueError(
                    f"{field_name} 的 Object Key 必須是字串"
                )
            normalized_object[cast(str, key)] = _normalize(
                item,
                field_name=field_name,
            )
        return normalized_object

    raise ValueError(
        f"{field_name} 包含不支援的 JSON 型別：{type(value).__name__}"
    )
