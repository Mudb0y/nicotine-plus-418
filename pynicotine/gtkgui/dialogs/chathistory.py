# SPDX-FileCopyrightText: 2022-2025 Nicotine+ Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import time

from collections import deque

from gi.repository import GObject

from pynicotine.config import config
from pynicotine.core import core
from pynicotine.events import events
from pynicotine.gtkgui.widgets import ui
from pynicotine.gtkgui.widgets.accelerator import Accelerator
from pynicotine.gtkgui.widgets.dialogs import Dialog
from pynicotine.gtkgui.widgets.theme import USER_STATUS_ICON_NAMES
from pynicotine.gtkgui.widgets.treeview import TreeView
from pynicotine.logfacility import log
from pynicotine.slskmessages import UserStatus
from pynicotine.utils import encode_path


class ChatHistory(Dialog):

    def __init__(self, application):

        (
            self.container,
            self.list_container,
            self.search_entry
        ) = ui.load(scope=self, path="dialogs/chathistory.ui")

        super().__init__(
            parent=application.window,
            content_box=self.container,
            title=_("Chat History"),
            width=960,
            height=700
        )

        self.list_view = TreeView(
            application.window, parent=self.list_container, activate_row_callback=self.on_show_user,
            search_entry=self.search_entry,
            columns={
                "status": {
                    "column_type": "icon",
                    "title": _("Status"),
                    "width": 25,
                    "hide_header": True
                },
                "user": {
                    "column_type": "text",
                    "title": _("User"),
                    "width": 175,
                    "iterator_key": True
                },
                "latest_message": {
                    "column_type": "text",
                    "title": _("Latest Message"),
                    "sort_column": "timestamp_data",
                    "default_sort_type": "descending"
                },

                # Hidden data columns
                "timestamp_data": {"data_type": GObject.TYPE_UINT64}
            }
        )

        Accelerator("<Primary>f", self.widget, self.on_search_accelerator)

        self.load_users()

        for event_name, callback in (
            ("server-login", self.server_login),
            ("server-disconnect", self.server_disconnect),
            ("user-status", self.user_status)
        ):
            events.connect(event_name, callback)

    def destroy(self):
        self.list_view.destroy()
        super().destroy()

    def server_login(self, msg):

        if not msg.success:
            return

        for iterator in self.list_view.iterators.values():
            username = self.list_view.get_row_value(iterator, "user")
            core.users.watch_user(username, context="chathistory")

    def server_disconnect(self, *_args):
        for iterator in self.list_view.iterators.values():
            self.list_view.set_row_value(iterator, "status", USER_STATUS_ICON_NAMES[UserStatus.OFFLINE])

    @staticmethod
    def load_user(file_path):
        """Reads the username and latest message from a given log file path.

        Usernames are first extracted from the file name. In case the
        extracted username contains underscores, attempt to fetch the
        original username from logged messages, since illegal filename
        characters are substituted with underscores.
        """

        username = os.path.basename(file_path[:-4]).decode("utf-8", "replace")
        is_safe_username = ("_" not in username)
        login_username = config.sections["server"]["login"]
        timestamp = os.path.getmtime(file_path)

        read_num_lines = 1 if is_safe_username else 25
        latest_message = None

        with open(file_path, "rb") as lines:
            lines = deque(lines, read_num_lines)

            for line in lines:
                try:
                    line = line.decode("utf-8")

                except UnicodeDecodeError:
                    line = line.decode("latin-1")

                if latest_message is None:
                    latest_message = line

                    if is_safe_username:
                        break

                    username_chars = set(username.replace("_", ""))

                if login_username in line:
                    continue

                if " [" not in line or "] " not in line:
                    continue

                start = line.find(" [") + 2
                end = line.find("] ", start)
                line_username_len = (end - start)

                if len(username) != line_username_len:
                    continue

                line_username = line[start:end]

                if username == line_username:
                    # Nothing to do, username is already correct
                    break

                if username_chars.issubset(line_username):
                    username = line_username
                    break

        return username, latest_message, timestamp

    def load_users(self):

        self.list_view.freeze()

        try:
            with os.scandir(encode_path(log.private_chat_folder_path)) as entries:
                for entry in entries:
                    if not entry.is_file() or not entry.name.endswith(b".log"):
                        continue

                    try:
                        username, latest_message, timestamp = self.load_user(entry.path)

                    except OSError:
                        continue

                    if latest_message is not None:
                        self.update_user(username, latest_message.strip(), timestamp)

        except OSError:
            pass

        self.list_view.unfreeze()

    def remove_user(self, username):

        iterator = self.list_view.iterators.get(username)

        if iterator is not None:
            self.list_view.remove_row(iterator)

        if not self.list_view.iterators:
            self.list_container.set_visible(False)

    def update_user(self, username, message, timestamp=None):

        self.remove_user(username)
        core.users.watch_user(username, context="chathistory")

        if not timestamp:
            timestamp_format = config.sections["logging"]["log_timestamp"]
            timestamp = time.time()
            h_timestamp = time.strftime(timestamp_format)
            message = f"{h_timestamp} [{username}] {message}"

        status = core.users.statuses.get(username, UserStatus.OFFLINE)

        self.list_view.add_row([
            USER_STATUS_ICON_NAMES[status],
            username,
            message,
            int(timestamp)
        ], select_row=False)

        if not self.list_container.get_visible():
            self.list_container.set_visible(True)

    def user_status(self, msg):

        iterator = self.list_view.iterators.get(msg.user)

        if iterator is None:
            return

        status_icon_name = USER_STATUS_ICON_NAMES.get(msg.status)

        if status_icon_name and status_icon_name != self.list_view.get_row_value(iterator, "status"):
            self.list_view.set_row_value(iterator, "status", status_icon_name)

    def on_show_user(self, *_args):

        for iterator in self.list_view.get_selected_rows():
            username = self.list_view.get_row_value(iterator, "user")

            core.privatechat.show_user(username)
            self.close()
            return

    def on_search_accelerator(self, *_args):
        """Ctrl+F - Search users."""

        self.search_entry.grab_focus()
        return True
