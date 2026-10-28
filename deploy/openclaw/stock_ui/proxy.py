"""Development entry point. The shared implementation is packaged with Mealie."""

from mealie.services.carrie_ui.proxy import (  # noqa: F401
    SCOPES,
    Config,
    annotate_send,
    app_factory,
    constrain_request,
    create_app,
    gateway_headers,
)
