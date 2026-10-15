"""
URL Block Function Module

This module provides functionality for managing URL blocking rules in CrowdStrike Falcon.
It delegates handling to specific modules in the `handlers` directory.
"""

# Handlers deliberately catch every exception to log it and return a 500 response.
# pylint: disable=broad-exception-caught

import traceback
from logging import Logger

from crowdstrike.foundry.function import Request, Response

from app_core import FUNC, APP_VERSION

# Import all handlers so they register their endpoints with FUNC
# pylint: disable=unused-import
import handlers.analytics
import handlers.categories
import handlers.policies
# pylint: enable=unused-import

@FUNC.handler(method='GET', path='/healthz')
def healthz(_request: Request, _: dict, logger: Logger) -> Response:
    """Basic health check — confirms the function is running."""
    logger.info("Starting /healthz handler")
    try:
        return Response(code=200, body={"status": "ok", "version": APP_VERSION})
    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to run healthz"})

if __name__ == '__main__':
    FUNC.run()
