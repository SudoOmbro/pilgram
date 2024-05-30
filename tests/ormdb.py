from orm.db import decode_progress, encode_progress


def test_decode_progress():
    assert decode_progress(None) == {}
    progress_dict = decode_progress(b"\x01\x00\x02\x00\x03\x00\x04\x00")
    items = list(progress_dict.items())
    assert len(items) == 2
    assert items[0][0] == 1
    assert items[0][1] == 2
    assert items[1][0] == 3
    assert items[1][1] == 4


def test_encode_progress():
    progress_dict = {1: 2, 3: 4}
    encoded_string = encode_progress(progress_dict)
    assert encoded_string == b"\x01\x00\x02\x00\x03\x00\x04\x00"
