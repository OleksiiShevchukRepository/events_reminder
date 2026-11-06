"""Entry point: starts Telegram polling, the scheduler and daily maintenance."""

import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand

from reminder_bot.bot.app import ALLOWED_UPDATES, build_dispatcher
from reminder_bot.bot.session import GatewayAwareSession
from reminder_bot.clock import SystemClock
from reminder_bot.config import Config, ConfigError, load_config
from reminder_bot.i18n import translate
from reminder_bot.scheduler.dispatcher import MessageDispatcher, RateLimiter
from reminder_bot.scheduler.maintenance import Maintenance
from reminder_bot.storage.db import Database
from reminder_bot.storage.repositories import Repository

logger = logging.getLogger("reminder_bot")

MAINTENANCE_CHECK_SECONDS = 3600
_COMMANDS = ("new", "list", "language", "help", "cancel")


async def _register_commands(bot: Bot) -> None:
    """Fill Telegram's command menu. A failure here shouldn't stop the bot."""
    try:
        for language, code in (("en", None), ("uk", "uk")):
            commands = [
                BotCommand(command=name, description=translate(language, f"command_{name}"))
                for name in _COMMANDS
            ]
            await bot.set_my_commands(commands, language_code=code)
    except TelegramAPIError as error:
        logger.warning("command_menu_not_set error=%s", type(error).__name__)


async def _maintenance_loop(maintenance: Maintenance) -> None:
    while True:
        try:
            await maintenance.run_if_due()
        except Exception:
            logger.exception("maintenance_failed")
        await asyncio.sleep(MAINTENANCE_CHECK_SECONDS)


async def run(config: Config) -> None:
    clock = SystemClock()
    db = await Database.open(config.database_path)
    await db.migrate()
    repo = Repository(db)
    interrupted = await repo.mark_leftover_sends_unknown(clock.now())
    if interrupted:
        logger.warning("interrupted_sends_marked_unknown count=%s", interrupted)

    bot = Bot(config.bot_token, session=GatewayAwareSession())
    dispatcher = build_dispatcher(repo, clock)
    scheduler = MessageDispatcher(
        repo=repo,
        bot=bot,
        clock=clock,
        limiter=RateLimiter(clock),
        heartbeat_path=config.heartbeat_path,
    )
    maintenance = Maintenance(db, repo, clock, config.backup_dir)

    await _register_commands(bot)
    scheduler_task = asyncio.create_task(scheduler.run())
    maintenance_task = asyncio.create_task(_maintenance_loop(maintenance))
    logger.info("bot_started")
    try:
        # Returns on SIGINT or SIGTERM. The session stays open so in-flight sends can finish.
        await dispatcher.start_polling(
            bot, allowed_updates=ALLOWED_UPDATES, close_bot_session=False
        )
    finally:
        logger.info("bot_stopping")
        await scheduler.stop()
        scheduler_task.cancel()
        maintenance_task.cancel()
        await asyncio.gather(scheduler_task, maintenance_task, return_exceptions=True)
        await bot.session.close()
        await db.close()
        logger.info("bot_stopped")


def main() -> None:
    try:
        config = load_config()
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    logging.basicConfig(
        level=config.log_level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
