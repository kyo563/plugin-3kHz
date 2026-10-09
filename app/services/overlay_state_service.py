from __future__ import annotations


from app.schemas.overlay_settings import OverlaySettings

class OverlayStateService:
    def __init__(self, *, onecomme: bool = False):
        self.onecomme = onecomme

    def _display_name(self, user: dict, mode: str) -> str:
        if user.get('is_placeholder'): return user.get('display_name', '')
        account = user.get('youtube_handle') or user.get('display_name', '')
        declared = user.get('declared_player_name') or user.get('youtube_nickname')
        if mode == 'declared': return declared or account
        if mode == 'youtube_declared' and declared and declared != account: return f"{account}（{declared}）"
        if mode == 'declared_youtube' and declared and declared != account: return f"{declared}（{account}）"
        return account

    def _to_overlay_user(self, user: dict, mode: str, session_counts: dict | None = None,
                         placeholder_label: str | None = None) -> dict:
        overlay_user = {"display_name": self._display_name(user, mode)}
        if user.get("is_placeholder"):
            overlay_user["is_placeholder"] = True
            if placeholder_label is not None:
                overlay_user['display_name'] = placeholder_label
        elif session_counts is not None:
            number = session_counts.get(user.get('user_id'), 0) + 1
            overlay_user['display_name'] += f" *{number}回目"
        return overlay_user

    def build_overlay_state(self, view_state: dict) -> dict:
        appearance = view_state.get('overlay_settings') or OverlaySettings().model_dump()
        placeholder_label = None
        if self.onecomme:
            key = 'placeholder_open_label' if view_state['is_open'] else 'placeholder_closed_label'
            placeholder_label = appearance.get(key)
            if placeholder_label is None:
                placeholder_label = '参加者募集中' if view_state['is_open'] else '-'
        show_declared = (view_state.get("overlay_settings") or {}).get("name_mode") or ("youtube_declared" if view_state.get("show_declared_player_name_on_overlay", False) else "youtube")
        session_counts = (view_state.get('session_participation_counts', {})
                          if (view_state.get('overlay_settings') or {}).get('show_participation_number', False)
                          else None)
        return {
            "is_open": view_state["is_open"],
            "now_view": [self._to_overlay_user(user, show_declared, session_counts, placeholder_label) for user in view_state["now_view"]],
            "next_view": [self._to_overlay_user(user, show_declared, session_counts, placeholder_label) for user in view_state["next_view"]],
            "queue_count": view_state["queue_count"],
            "queue_group_count": view_state["queue_group_count"],
            "total_waiting_count": view_state["total_waiting_count"],
            "total_waiting_group_count": view_state["total_waiting_group_count"],
            "appearance": appearance,
        }
