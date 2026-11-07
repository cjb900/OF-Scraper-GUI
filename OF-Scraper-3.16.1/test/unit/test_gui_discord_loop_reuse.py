"""The GUI resets the logger before every scrape, which builds a new Discord
handler each time. Each handler used to make its own event loop and never
close it, so every scrape left an open loop (two sockets on Windows) behind.
"""

import asyncio
import threading

import ofscraper.utils.config.data as data
import ofscraper.utils.logs.classes.handlers.discord as discord


def test_handlers_on_one_thread_share_one_loop(monkeypatch):
    monkeypatch.setattr(data, "get_discord", lambda: "")
    first = discord.DiscordHandler()
    first.close()
    second = discord.DiscordHandler()
    second.close()
    assert first.loop is second.loop
    assert asyncio.get_event_loop_policy().get_event_loop() is second.loop


def test_a_closed_loop_is_replaced(monkeypatch):
    monkeypatch.setattr(data, "get_discord", lambda: "")
    first = discord.DiscordHandler()
    first.close()
    first.loop.close()
    second = discord.DiscordHandler()
    second.close()
    assert second.loop is not first.loop and not second.loop.is_closed()


def test_each_thread_gets_its_own_loop(monkeypatch):
    monkeypatch.setattr(data, "get_discord", lambda: "")
    main = discord.DiscordHandler()
    main.close()
    seen = {}

    def other():
        h = discord.DiscordHandler()
        h.close()
        seen["loop"] = h.loop
        h.loop.close()
        asyncio.set_event_loop(None)

    t = threading.Thread(target=other)
    t.start()
    t.join()
    assert seen["loop"] is not main.loop
