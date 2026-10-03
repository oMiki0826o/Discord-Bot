"""bot/mod/message/autoreply/__init__.py

Modification():

- Message auto-reply rules and runtime services。"""
from bot.mod.message.autoreply.model import AutoReplyDocument, AutoReplyRule, MatchMode

__all__ = ("AutoReplyDocument", "AutoReplyRule", "MatchMode")
