import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.declared_player_name_parser import DeclaredPlayerNameParser


def test_parse_declared_name_success_cases():
    parser = DeclaredPlayerNameParser()
    assert parser.parse("参加希望 名前 たなかたろう") == "たなかたろう"
    assert parser.parse("こんにちは参加希望 名前 たなかたろう") == "たなかたろう"
    assert parser.parse("参加希望です 名前 たなかたろう") == "たなかたろう"
    assert parser.parse("参加希望 名前 B") == "B"


def test_parse_declared_name_none_cases():
    parser = DeclaredPlayerNameParser()
    assert parser.parse("参加希望 たなかたろう") is None
    assert parser.parse("参加希望 name たなかたろう") is None
    assert parser.parse("参加希望 ネーム たなかたろう") is None
    assert parser.parse("参加希望 プレイヤー名 たなかたろう") is None
    assert parser.parse("参加希望 名前") is None
    assert parser.parse("参加辞退 名前 たなかたろう") is None
    assert parser.parse("参加を辞退 名前 たなかたろう") is None


def test_parse_declared_name_trims_and_truncates_to_32_chars():
    parser = DeclaredPlayerNameParser()
    long_name = "a" * 33
    assert parser.parse(f"参加希望 名前 {long_name}") == "a" * 32
