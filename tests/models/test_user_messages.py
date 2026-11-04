import logging

import pytest

from src.models.user_messages import UserMessages, add_user_info, add_user_warning, current_user_messages


class TestUserMessages:
    def test_collects_warnings_and_infos(self):
        messages = UserMessages()
        messages.warnings.append("warning 1")
        messages.infos.append("info 1")
        assert messages.warnings == ["warning 1"]
        assert messages.infos == ["info 1"]

    def test_starts_empty(self):
        messages = UserMessages()
        assert messages.warnings == []
        assert messages.infos == []


class TestAddUserWarning:
    def test_collects_warning_when_context_active(self):
        messages = UserMessages()
        token = current_user_messages.set(messages)
        try:
            add_user_warning("test warning")
            assert messages.warnings == ["test warning"]
        finally:
            current_user_messages.reset(token)

    def test_does_not_fail_without_context(self, caplog: pytest.LogCaptureFixture):
        """add_user_warning still logs even without an active context."""
        add_user_warning("orphan warning")
        assert "orphan warning" in caplog.text

    def test_logs_warning(self, caplog: pytest.LogCaptureFixture):
        messages = UserMessages()
        token = current_user_messages.set(messages)
        try:
            add_user_warning("logged warning")
            assert "logged warning" in caplog.text
        finally:
            current_user_messages.reset(token)


class TestAddUserInfo:
    def test_collects_info_when_context_active(self):
        messages = UserMessages()
        token = current_user_messages.set(messages)
        try:
            add_user_info("test info")
            assert messages.infos == ["test info"]
        finally:
            current_user_messages.reset(token)

    def test_does_not_fail_without_context(self, caplog: pytest.LogCaptureFixture):
        """add_user_info still logs even without an active context."""
        with caplog.at_level(logging.INFO):
            add_user_info("orphan info")
            assert "orphan info" in caplog.text


class TestContextIsolation:
    def test_separate_contexts_do_not_share_messages(self):
        """Two UserMessages instances don't interfere with each other."""
        messages_a = UserMessages()
        token_a = current_user_messages.set(messages_a)
        add_user_warning("warning A")
        current_user_messages.reset(token_a)

        messages_b = UserMessages()
        token_b = current_user_messages.set(messages_b)
        add_user_warning("warning B")
        current_user_messages.reset(token_b)

        assert messages_a.warnings == ["warning A"]
        assert messages_b.warnings == ["warning B"]
