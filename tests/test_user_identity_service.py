import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.services.user_identity_service import UserIdentityService


def test_user_identity_stable_and_hidden_raw_key():
    s = UserIdentityService()
    a = s.build_comment_user_id('yt', 'raw-1')
    b = s.build_comment_user_id('yt', 'raw-1')
    c = s.build_comment_user_id('yt', 'raw-2')
    assert a == b
    assert a != c
    assert 'raw-1' not in a
