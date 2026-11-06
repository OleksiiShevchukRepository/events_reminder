import json

import pytest
from aiogram import Bot
from aiogram.exceptions import ClientDecodeError, TelegramForbiddenError, TelegramServerError
from aiogram.methods import GetMe

from reminder_bot.bot.session import GatewayAwareSession, TelegramGatewayError

HTML_ERROR_PAGE = "<html><body><h1>502 Bad Gateway</h1></body></html>"


def error_body(code: int, description: str) -> str:
    return json.dumps({"ok": False, "error_code": code, "description": description})


@pytest.fixture
def session() -> GatewayAwareSession:
    return GatewayAwareSession()


@pytest.fixture
def bot(session: GatewayAwareSession) -> Bot:
    return Bot("123456:TEST", session=session)


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gateway_statuses_are_recognized_even_with_an_html_body(session, bot, status: int) -> None:
    with pytest.raises(TelegramGatewayError):
        session.check_response(bot, GetMe(), status, HTML_ERROR_PAGE)


def test_500_is_a_plain_server_error(session, bot) -> None:
    with pytest.raises(TelegramServerError) as caught:
        session.check_response(bot, GetMe(), 500, error_body(500, "Internal Server Error"))
    assert not isinstance(caught.value, TelegramGatewayError)


def test_other_errors_are_unchanged(session, bot) -> None:
    with pytest.raises(TelegramForbiddenError):
        session.check_response(bot, GetMe(), 403, error_body(403, "Forbidden"))
    with pytest.raises(ClientDecodeError):
        session.check_response(bot, GetMe(), 500, HTML_ERROR_PAGE)
