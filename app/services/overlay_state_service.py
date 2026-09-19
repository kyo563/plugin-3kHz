from __future__ import annotations


from app.schemas.overlay_settings import OverlaySettings

class OverlayStateService:
    def _display_name(self, user: dict, mode: str) -> str:
        if user.get('is_placeholder'): return user.get('display_name', '')
        account = user.get('youtube_handle') or user.get('display_name', '')
        declared = user.get('declared_player_name') or user.get('youtube_nickname')
        if mode == 'declared': return declared or account
        if mode == 'youtube_declared' and declared and declared != account: return f"{account}（{declared}）"
        if mode == 'declared_youtube' and declared and declared != account: return f"{declared}（{account}）"
        return account

    def _to_overlay_user(self, user: dict, mode: str) -> dict:
        overlay_user = {"display_name": self._display_name(user, mode)}
        if user.get("is_placeholder"): overlay_user["is_placeholder"] = True
        return overlay_user

    def build_overlay_state(self, view_state: dict) -> dict:
        show_declared = (view_state.get("overlay_settings") or {}).get("name_mode") or ("youtube_declared" if view_state.get("show_declared_player_name_on_overlay", False) else "youtube")
        return {
            "is_open": view_state["is_open"],
            "now_view": [self._to_overlay_user(user, show_declared) for user in view_state["now_view"]],
            "next_view": [self._to_overlay_user(user, show_declared) for user in view_state["next_view"]],
            "queue_count": view_state["queue_count"],
            "queue_group_count": view_state["queue_group_count"],
            "total_waiting_count": view_state["total_waiting_count"],
            "total_waiting_group_count": view_state["total_waiting_group_count"],
            "appearance": view_state.get("overlay_settings", OverlaySettings().model_dump()),
        }
