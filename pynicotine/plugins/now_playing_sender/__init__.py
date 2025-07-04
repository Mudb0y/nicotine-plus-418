# SPDX-FileCopyrightText: 2020-2025 Nicotine+ Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Gio
from pynicotine.pluginsystem import BasePlugin


class Plugin(BasePlugin):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.settings = {
            "rooms": ["testroom"]
        }
        self.metasettings = {
            "rooms": {
                "description": "Rooms to broadcast in",
                "type": "list string"
            }
        }

        self.last_song_url = ""
        self.stop = False

        self.bus = Gio.bus_get_sync(bus_type=Gio.BusType.SESSION)
        self.signal_id = None
        self.dbus_mpris_service = "org.mpris.MediaPlayer2."

        self.add_mpris_signal_receiver()

    def disable(self):
        self.remove_mpris_signal_receiver()

    def add_mpris_signal_receiver(self):
        """Receive updates related to MPRIS."""

        self.signal_id = self.bus.signal_subscribe(
            sender=None,
            interface_name="org.freedesktop.DBus.Properties",
            member="PropertiesChanged",
            object_path="/org/mpris/MediaPlayer2",
            arg0=None,
            flags=0,
            callback=self.song_change,
            user_data=None
        )

    def remove_mpris_signal_receiver(self):
        """Stop receiving updates related to MPRIS."""

        self.bus.signal_unsubscribe(self.signal_id)

    def get_current_mpris_player(self):
        """Returns the MPRIS client currently selected in Now Playing."""

        player = self.config.sections["players"]["npothercommand"]

        if not player:
            dbus_proxy = Gio.DBusProxy.new_sync(
                connection=self.bus,
                flags=0,
                info=None,
                name="org.freedesktop.DBus",
                object_path="/org/freedesktop/DBus",
                interface_name="org.freedesktop.DBus",
                cancellable=None
            )
            names = dbus_proxy.ListNames()

            for name in names:
                if name.startswith(self.dbus_mpris_service):
                    player = name[len(self.dbus_mpris_service):]
                    break

        return player

    def get_current_mpris_song_url(self, player):
        """Returns the current song url for the selected MPRIS client."""

        dbus_proxy = Gio.DBusProxy.new_sync(
            connection=self.bus,
            flags=0,
            info=None,
            name=self.dbus_mpris_service + player,
            object_path="/org/mpris/MediaPlayer2",
            interface_name="org.freedesktop.DBus.Properties",
            cancellable=None
        )
        metadata = dbus_proxy.Get("(ss)", "org.mpris.MediaPlayer2.Player", "Metadata")
        song_url = metadata.get("xesam:url")

        return song_url

    def send_now_playing(self):
        """Broadcast Now Playing in selected rooms."""

        for room in self.settings["rooms"]:
            playing = self.core.now_playing.get_np()

            if playing:
                self.send_public(room, playing)

    def song_change(self, _connection, _sender_name, _object_path, _interface_name,
                    _signal_name, parameters, _user_data):

        if self.config.sections["players"]["npplayer"] != "mpris":
            # MPRIS is not active, exit
            return

        # Get the changed song url received from the the signal
        try:
            changed_song_url = parameters[1].get("Metadata").get("xesam:url")

        except AttributeError:
            return

        if not changed_song_url:
            # Song url empty, the player most likely stopped playing
            self.last_song_url = ""
            return

        if changed_song_url == self.last_song_url:
            # A new song didn't start playing, exit
            return

        try:
            player = self.get_current_mpris_player()
            selected_client_song_url = self.get_current_mpris_song_url(player)

        except Exception as error:
            # Selected player is invalid
            self.log("Cannot retrieve currently playing song. Error: %s", error)
            return

        if selected_client_song_url != changed_song_url:
            # Song change was from another MPRIS client than the selected one, exit
            return

        # Keep track of which song is playing
        self.last_song_url = changed_song_url

        self.send_now_playing()
