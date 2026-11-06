"""An aiogram session that can tell a gateway error from other server errors.

aiogram raises the same error for every 5xx and can't parse a gateway's HTML error
page at all. A 502, 503 or 504 usually means the request never reached Telegram's
bot servers, so it's retried, while the outcome of a 500 is unknown (see research.md).
"""

from http import HTTPStatus
from typing import Any

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramServerError
from aiogram.methods import TelegramMethod

_GATEWAY_STATUSES = {
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.SERVICE_UNAVAILABLE,
    HTTPStatus.GATEWAY_TIMEOUT,
}


class TelegramGatewayError(TelegramServerError):
    """Telegram's gateway answered 502, 503 or 504."""


class GatewayAwareSession(AiohttpSession):
    def check_response(
        self, bot: Bot, method: TelegramMethod[Any], status_code: int, content: str
    ) -> Any:
        if status_code in _GATEWAY_STATUSES:
            raise TelegramGatewayError(method=method, message=f"HTTP {status_code}")
        return super().check_response(bot, method, status_code, content)
