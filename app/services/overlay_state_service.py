from __future__ import annotations


class OverlayStateService:
    def _to_overlay_user(self, user: dict) -> dict:
        overlay_user = {"display_name": user.get("display_name", "")}
        if user.get("is_placeholder"):
            overlay_user["is_placeholder"] = True
        return overlay_user

    def build_overlay_state(self, view_state: dict) -> dict:
        return {
            "is_open": view_state["is_open"],
            "now_view": [self._to_overlay_user(user) for user in view_state["now_view"]],
            "next_view": [self._to_overlay_user(user) for user in view_state["next_view"]],
            "queue_count": view_state["queue_count"],
            "queue_group_count": view_state["queue_group_count"],
        }
