from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass

TAG_END = 0
TAG_METADATA = 77
TAG_DEFINE_BINARY_DATA = 87


class BmodError(Exception):
    pass


@dataclass
class BmodData:
    metadata: dict
    files_by_id: dict


def _skip_rect(data: bytes, offset: int) -> int:
    nbits = data[offset] >> 3
    total_bits = 5 + 4 * nbits
    return offset + (total_bits + 7) // 8


def _read_tag_header(data: bytes, offset: int):
    if offset + 2 > len(data):
        return None
    tag_code_and_length = struct.unpack_from("<H", data, offset)[0]
    tag_type = tag_code_and_length >> 6
    tag_length = tag_code_and_length & 0x3F
    offset += 2
    if tag_length == 0x3F:
        if offset + 4 > len(data):
            return None
        tag_length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
    return tag_type, tag_length, offset


def parse_bmod(raw: bytes) -> BmodData:
    if len(raw) < 8:
        raise BmodError("File too small to be a .bmod/.swf.")

    signature = raw[0:3]
    if signature == b"CWS":
        try:
            data = zlib.decompress(raw[8:])
        except zlib.error as e:
            raise BmodError(f"Could not decompress .bmod (zlib): {e}") from e
    elif signature == b"FWS":
        data = raw[8:]
    elif signature == b"ZWS":
        raise BmodError("LZMA-compressed .bmod files aren't supported by this reader.")
    else:
        raise BmodError("Not a recognizable .bmod/.swf file (bad signature).")

    offset = _skip_rect(data, 0)
    offset += 4

    metadata = None
    files_by_id: dict[int, bytes] = {}

    while True:
        header = _read_tag_header(data, offset)
        if header is None:
            break
        tag_type, tag_length, offset = header
        if tag_type == TAG_END and tag_length == 0:
            break

        tag_body = data[offset:offset + tag_length]

        if tag_type == TAG_METADATA:
            text = tag_body.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
            try:
                metadata = json.loads(text)
            except json.JSONDecodeError as e:
                raise BmodError(f"Metadata tag isn't valid JSON: {e}") from e

        elif tag_type == TAG_DEFINE_BINARY_DATA:
            if len(tag_body) >= 6:
                char_id = struct.unpack_from("<H", tag_body, 0)[0]
                files_by_id[char_id] = tag_body[6:]

        offset += tag_length

    if metadata is None:
        raise BmodError(
            "No Metadata tag found in this .bmod — it may use a different/older "
            "format than BhModCreator's, or isn't a mod file at all."
        )

    return BmodData(metadata=metadata, files_by_id=files_by_id)
