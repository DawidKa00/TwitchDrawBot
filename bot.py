import traceback
from python_twitch_irc import TwitchIrc
from dotenv import load_dotenv
import os
import socket
import sqlite3
import PySimpleGUI as sg
from collections import namedtuple

load_dotenv()
PARTICIPATE_COMMANDS = []

Message = namedtuple(
    'Message',
    'prefix user channel irc_command irc_args badge_info text text_command text_args',
)

channel = None


class SqLite:
    def __init__(self):
        self.conn = None
        self.sub_conn = None
        self.gui = GUI.get_instance()

    def addToDB(self, username, subscriber):
        self.conn.execute("INSERT OR IGNORE INTO users (username, subscriber) VALUES (?, ?)", (username, subscriber))
        self.conn.commit()
        self.gui.update_participants()

    def __enter__(self):
        self.conn = sqlite3.connect('database.db')
        self.conn.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, subscriber INTEGER)")
        self.conn.commit()
        self.sub_conn = sqlite3.connect('sub_database.db')
        self.sub_conn.execute("CREATE TABLE IF NOT EXISTS sub_users(username TEXT)")
        self.sub_conn.commit()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_value, tb)
        self.conn.close()
        self.sub_conn.close()

    def sub_db(self, sub_luck):
        cursor1 = self.conn.cursor()
        cursor1.execute("SELECT username, subscriber FROM users")
        users = cursor1.fetchall()

        cursor2 = self.sub_conn.cursor()

        for user in users:
            user_name = user[0]
            subscriber = user[1]
            for _ in range(int(sub_luck)) if subscriber == 1 else range(1):
                cursor2.execute("INSERT INTO sub_users (username) VALUES (?)", (user_name,))

        self.sub_conn.commit()

    def random(self):
        sub_cursor = self.sub_conn.cursor()
        sub_cursor.execute("SELECT username FROM sub_users ORDER BY RANDOM() LIMIT 1")
        result = sub_cursor.fetchone()
        if result:
            return result[0]
        else:
            return None

    def clear(self):
        cursor = self.conn.cursor()
        sub_cursor = self.sub_conn.cursor()
        sub_cursor.execute("DELETE FROM sub_users")
        cursor.execute("DELETE FROM users")
        self.conn.commit()
        self.sub_conn.commit()

    def count(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        result = cursor.fetchone()
        count = result[0]
        return count


class GUI:
    __instance = None

    def __init__(self):
        sg.theme('Green')
        self.layout = [
            [sg.Text("Participate command:", justification='center'),
             sg.InputText(size=50, default_text="!ticket,|letmein", key="-commands-")],
            # You can change default channel name in the "default_text" field below
            [sg.Text("Channel name:"), sg.InputText(size=13, default_text="", key="-channel_name-"),
             sg.Text("Sub luck:"), sg.InputText(size=5, default_text="3", key="-sub_luck-")],
            [sg.Button("Open entry", size=(10, 3), expand_x=True),
             sg.Button("Close", size=(10, 3), expand_x=True),
             sg.Button("Draw", size=(10, 3), expand_x=True),
             sg.Button("Clear database", size=(10, 3), expand_x=True)],
            [sg.Text("Disconnected", key="-status-")],

            [sg.Text("WINNER", expand_x=True, expand_y=True, justification='center', font=("italic", 30, "bold"))],

            [sg.Text("", expand_x=True, expand_y=True, justification='center', key="-winner-",
                     font=("italic", 30, "bold"))],

            [sg.Text("Participants: 0", key="-counter-", justification='right')]

        ]
        self.title = "Twitch draw bot"
        self.size = (800, 600)
        self.window = sg.Window(self.title, self.layout, size=self.size, resizable=True, finalize=True)
        if GUI.__instance is None:
            GUI.__instance = self
        self.bot = TwitchBot.get_instance()
        self.open_window()

    @staticmethod
    def get_instance():
        if GUI.__instance is None:
            GUI()
        return GUI.__instance

    def open_window(self):
        with SqLite() as sqlite:
            while True:
                event, self.values = self.window.read()
                if event == "Open entry":
                    self.channel_name()
                    self.open_entry()
                elif event == "Close":
                    self.bot.close()
                    sqlite.sub_db(self.values['-sub_luck-'])
                elif event == "Draw":
                    self.bot.draw()
                elif event == "Clear database":
                    sqlite.clear()
                    self.update_participants()
                elif event == sg.WIN_CLOSED:
                    sqlite.clear()
                    break

            self.window.close()

    def open_entry(self):
        global PARTICIPATE_COMMANDS
        PARTICIPATE_COMMANDS = self.values['-commands-'].split(',')
        self.window.start_thread(lambda: self.bot.connect(), "")

    def channel_name(self):
        global channel
        channel = self.values['-channel_name-']

    def draw(self, winner):
        self.window['-winner-'].update(winner)

    def update_participants(self):
        with SqLite() as sqlite:
            self.window['-counter-'].update(f"Participants: {sqlite.count()}")

    def status(self, connected, is_opened):
        if is_opened:
            if connected:
                self.window['-status-'].update("Connected: Open")
            else:
                self.window['-status-'].update("Disconnected")
        else:
            if connected:
                self.window['-status-'].update("Connected: Closed")
            else:
                self.window['-status-'].update("Disconnected")


class TwitchBot(TwitchIrc):
    __instance = None

    def __init__(self):
        self.is_opened = False
        self._connected = False
        self.irc_server = 'irc.twitch.tv'
        self.irc_port = 6667
        self.irc = socket.socket()
        self.oauth_token = os.getenv("OAUTH_TOKEN")
        self.username = os.getenv("USER_NAME")
        self.gui = GUI.get_instance()
        self.channel = channel
        if TwitchBot.__instance is None:
            TwitchBot.__instance = self

    @staticmethod
    def get_instance():
        if TwitchBot.__instance is None:
            TwitchBot()
        return TwitchBot.__instance

    def send_privmsg(self, channel, text):
        self.send_command(f'PRIVMSG #{channel} :{text}')

    def send_command(self, command):
        if 'PASS' not in command:
            print(f'< {command}')

        self.irc.send((command + '\r\n').encode())

    def send_raw(self, message):
        self.irc.sendall(bytes(message, 'utf-8'))

    def connect(self):
        if not self._connected:
            self.irc.connect((self.irc_server, self.irc_port))
            self.send_command(f'PASS {self.oauth_token}')
            self.send_command(f'NICK {self.username}')
            self.send_command(f'JOIN #{channel}')
            self.send_raw('CAP REQ :twitch.tv/tags\r\n')
            self._connected = True
            self.is_opened = True
            self.gui.status(self._connected, self.is_opened)
            self.loop_for_messages()
        else:
            self.open()

    @staticmethod
    def get_user_from_prefix(prefix):
        domain = prefix.split('!')[0]
        if domain.endswith('.tmi.twitch.tv'):
            return domain.replace('.tmi.twitch.tv', '')
        if 'tmi.twitch.tv' not in domain:
            return domain
        return None

    def parse_message(self, received_msg):
        parts = received_msg.split(' ')
        prefix = None
        user = None
        channel = None
        text = None
        text_command = None
        text_args = None
        badge_info = None
        irc_command = None
        irc_args = None

        if parts[0].startswith(':'):
            prefix = parts[0][1:]
            user = self.get_user_from_prefix(prefix)
            parts = parts[1:]

        elif parts[0].startswith('@'):
            prefix = parts[1][1:]
            user = self.get_user_from_prefix(prefix)
            badge_info = parts[0]
            parts = parts[2:]

        text_start = next(
            (idx for idx, part in enumerate(parts) if part.startswith(':')),
            None
        )
        if text_start is not None:
            text_parts = parts[text_start:]
            text_parts[0] = text_parts[0][1:]
            text = ' '.join(text_parts)
            text_command = text_parts[0]
            text_args = text_parts[1:]
            parts = parts[:text_start]

        irc_command = parts[0]
        irc_args = parts[1:]

        hash_start = next(
            (idx for idx, part in enumerate(irc_args) if part.startswith('#')),
            None
        )
        if hash_start is not None:
            channel = irc_args[hash_start][1:]

        message = Message(
            prefix=prefix,
            user=user,
            channel=channel,
            text=text,
            text_command=text_command,
            text_args=text_args,
            badge_info=badge_info,
            irc_command=irc_command,
            irc_args=irc_args,
        )
        return message

    def handle_template_command(self, message, text_command, template):
        text = template.format(**{'message': message})
        self.send_privmsg(message.channel, text)

    def handle_message(self, received_msg):
        if len(received_msg) == 0:
            return
        message = self.parse_message(received_msg)

        if message.irc_command == 'PING':
            self.send_command('PONG :tmi.twitch.tv')

        if message.irc_command == 'PRIVMSG':
            if message.text_command in PARTICIPATE_COMMANDS:
                if self._connected and self.is_opened:
                    with SqLite() as sqlite:
                        if "subscriber=0" in message.badge_info:
                            sqlite.addToDB(message.user, False)
                        else:
                            sqlite.addToDB(message.user, True)

    def loop_for_messages(self):
        while self._connected and self.is_opened:
            try:
                print("Waiting for msgs")
                received_msgs = self.irc.recv(4096).decode()
                for received_msg in received_msgs.split('\r\n'):
                    self.handle_message(received_msg)
            except:
                self.is_opened = False
                self._connected = False

    @staticmethod
    def draw():
        with SqLite() as sqlite:
            winner = sqlite.random()
        if winner:
            print("Random nickname: ", winner)
            GUI.get_instance().draw(winner)
        else:
            print("There is no one in database")

    def close(self):
        self.is_opened = False
        self.gui.status(self._connected, self.is_opened)

    def open(self):
        self.is_opened = True
        self.gui.status(self._connected, self.is_opened)
        self.loop_for_messages()


def main():
    GUI.get_instance()


if __name__ == '__main__':
    main()
