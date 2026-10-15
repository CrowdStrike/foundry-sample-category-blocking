"""Shared Foundry function instance, version constants and FalconPy client factory."""

from crowdstrike.foundry.function import Function

# Initialize FUNCtion
FUNC = Function.instance()

# ---------------------------------------------------------------------------
# Version Constants
# ---------------------------------------------------------------------------
COLLECTION_DOMAIN_VER = "v2.0"
COLLECTION_RELATION_VER = "v5.0"
APP_VERSION = "1.2.0"


def get_client(client_class):
    """
    Return a new FalconPy client for the given class.

    Clients are created per request so they always authenticate with the
    current Foundry function credentials.
    """
    return client_class(debug=False)
