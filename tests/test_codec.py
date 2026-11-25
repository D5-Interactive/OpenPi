from io import BytesIO

import pytest

from openpi.protocol.codec import encode_record, iter_records


def test_encode_record_is_one_compact_json_line():
    assert encode_record({"type": "get_state", "id": "1"}) == b'{"type":"get_state","id":"1"}\n'


def test_iter_records_splits_on_lf_and_skips_blank_lines():
    stream = BytesIO(b'{"a":1}\n\n{"b":2}\n')
    assert list(iter_records(stream)) == [{"a": 1}, {"b": 2}]


def test_iter_records_accepts_crlf():
    assert list(iter_records(BytesIO(b'{"a":1}\r\n'))) == [{"a": 1}]


def test_unicode_line_separator_inside_a_string_does_not_split_the_record():
    text = '{"text":"one\u2028two"}'.encode("utf-8") + b"\n"
    assert list(iter_records(BytesIO(text))) == [{"text": "one\u2028two"}]


def test_invalid_json_raises():
    with pytest.raises(ValueError):
        list(iter_records(BytesIO(b"{not json}\n")))
