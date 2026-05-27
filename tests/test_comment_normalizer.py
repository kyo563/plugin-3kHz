import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.comment_normalizer import CommentNormalizer


def test_trims_spaces():
    assert CommentNormalizer().normalize("  参加希望  ") == "参加希望"


def test_normalizes_full_width_space_and_collapses_spaces():
    assert CommentNormalizer().normalize("参加　　希望") == "参加 希望"


def test_treats_newline_and_tab_as_spaces():
    assert CommentNormalizer().normalize("参加\n\t希望") == "参加 希望"


def test_normalizes_full_width_alnum_and_lowercases_ascii():
    assert CommentNormalizer().normalize("ＡＢＣ１２３") == "abc123"


def test_keeps_symbols_and_emoji():
    assert CommentNormalizer().normalize(" 参加希望！😀 ") == "参加希望!😀"
