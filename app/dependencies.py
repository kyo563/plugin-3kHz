from fastapi import Request

from app.services.application_services import ApplicationServices


def get_services(request: Request | None) -> ApplicationServices:
    if request is None:
        # Compatibility only for older Python callers; HTTP always supplies Request.
        from app.mock_state import get_legacy_services
        return get_legacy_services()
    return request.app.state.services
