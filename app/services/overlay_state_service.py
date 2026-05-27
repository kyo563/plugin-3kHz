from __future__ import annotations


class OverlayStateService:
    def _display_name(self, user: dict, show_declared: bool) -> str:
        declared = user.get("declared_player_name")
        if show_declared and declared and not user.get("is_placeholder"):
            return f"{user.get('display_name', '')}（{declared}）"
        return user.get("display_name", "")

    def _to_overlay_user(self, user: dict, show_declared: bool) -> dict:
        overlay_user = {"display_name": self._display_name(user, show_declared)}
        if user.get("is_placeholder"):
            overlay_user["is_placeholder"] = True
        return overlay_user

    def build_overlay_state(self, view_state: dict) -> dict:
        show_declared = view_state.get("show_declared_player_name_on_overlay", False)
        return {
            "is_open": view_state["is_open"],
            "show_declared_player_name_on_overlay": show_declared,
            "now_view": [self._to_overlay_user(user, show_declared) for user in view_state["now_view"]],
            "next_view": [self._to_overlay_user(user, show_declared) for user in view_state["next_view"]],
            "queue_count": view_state["queue_count"],
            "queue_group_count": view_state["queue_group_count"],
        }
