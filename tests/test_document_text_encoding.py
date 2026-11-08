"""Students' text files must never silently replace undecodable Chinese bytes."""
import pytest

from server.proposal.documents import extract_file


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gbk", "gb18030", "utf-16"])
def test_chinese_text_is_preserved_across_common_encodings(encoding):
    source = "姓名：李明\n专业：计算机\n绩点：3.8"
    extraction = extract_file("成绩说明.txt", source.encode(encoding))
    assert extraction.status == "ready"
    assert all(part in extraction.text for part in ("李明", "计算机", "3.8"))
    assert "�" not in extraction.text
    if encoding in ("gbk", "gb18030"):
        assert "中文文本编码" in extraction.warning


@pytest.mark.parametrize("data", [b"\xff\xff\xff", b"a\x00b\x00"])
def test_unreadable_text_produces_an_error_instead_of_replacement_characters(data):
    with pytest.raises(ValueError, match="UTF-8"):
        extract_file("说明.txt", data)


def test_visible_replacement_character_in_source_is_not_silently_ignored():
    extraction = extract_file("说明.txt", "原文中已有乱码 �".encode())
    assert "替换字符" in extraction.warning
