import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.command_detector import CommandDetector


def test_join_cases():
    detector = CommandDetector()
    for message in ["参加希望", "参加希望します", "参加希望です", "こんにちは参加希望", "参加希望 名前 たなかたろう", "参加希望でお願いします"]:
        assert detector.detect(message) == "join"


def test_join_ignore_cases():
    detector = CommandDetector()
    for message in [
        "参加", "参加したい", "参加します", "さんか", "sanka", "join", "希望", "参加 希望", "参加きぼう"
    ]:
        assert detector.detect(message) == "ignore"


def test_cancel_cases():
    detector = CommandDetector()
    for message in ["参加辞退", "参加辞退します", "参加辞退でお願いします", "参加を辞退", "参加を辞退します", "すみません参加を辞退します"]:
        assert detector.detect(message) == "cancel"


def test_cancel_ignore_cases():
    detector = CommandDetector()
    for message in ["辞退", "辞退します", "参加やめます", "やめます", "取消", "取り消し", "キャンセル", "cancel", "参加キャンセル", "参加をやめます"]:
        assert detector.detect(message) == "ignore"


def test_cancel_priority_over_join():
    detector = CommandDetector()
    assert detector.detect("参加希望したけど参加辞退します") == "cancel"
    assert detector.detect("参加希望、やっぱり参加を辞退します") == "cancel"


def test_join_excludes_are_ignore():
    detector = CommandDetector()
    assert detector.detect("参加希望者") == "ignore"
    assert detector.detect("参加希望順") == "ignore"
    assert detector.detect("参加希望者多いね") == "ignore"
    assert detector.detect("参加希望順どうなっていますか") == "ignore"
