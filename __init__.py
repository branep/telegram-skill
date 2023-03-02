from mycroft import MycroftSkill, intent_file_handler
from mycroft_bus_client import MessageBusClient, Message
from mycroft.audio import wait_while_speaking
from alsaaudio import Mixer
import requests
import json


class Telegram(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

    def initialize(self):
        self.first_run = True
        self.backoff_count = 0
        self.backoff_limit = 60
        self.check_wait = 5
        self.update_id_offset = 0
        self.token = self.settings.get("token")
        self.schedule_repeating_event(
            self.check_bot, None, self.check_wait, 'CheckTelegramBot')
        try:
            self.mixer = Mixer()
        except Exception as e:
            self.log.error(e)
        self.add_event('telegram-skill:response', self.send_handler)
        self.add_event('speak', self.response_handler)
        self.msg_queue = []

    def check_bot(self):
        if self.backoff_count <= self.backoff_limit:
            self.backoff_count = self.backoff_count + 1
        else:
            if self.check_wait != 60:
                self.log.info("Backing off the Telegram checks")
                self.check_wait = 60
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates?offset={self.update_id_offset}"
            update = requests.get(url).json()
            if update['ok']:
                for post in update['result']:
                    if not self.first_run:
                        self.check_wait = 5
                        self.backoff_count = 0
                        self.msg_queue.append(post)
                        self.update_id_offset = str(int(post['update_id'])+1)
                        self.typing_action(post['message']['chat']['id'])
                        self.ask_mycroft(post['message']['text'])
                    else:
                        self.update_id_offset = str(int(post['update_id'])+1)
                self.first_run = False
            else:
                return False
        except Exception as e:
            self.log.error(e)
            return False

    def send_handler(self, message):
        reply = message.data.get("utterance")
        if not self.msg_queue:
            self.log.warning("Message queue is empty, but trying to reply")
        else:
            post = self.msg_queue.pop(0)
            if 'message' in post:
                data = {
                    "chat_id": post['message']['chat']['id'],
                    "text": reply,
                    "reply_to_message_id": post['message']['message_id']
                }
                url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                r = requests.post(url, data).json()
            else:
                self.log.warning("")

    def typing_action(self, chat_id):
        data = {
            "chat_id": chat_id,
            "action": "typing"
        }
        url = f"https://api.telegram.org/bot{self.token}/sendChatAction"
        r = requests.post(url, data).json()

    def ask_mycroft(self, text):
        self.add_event('recognizer_loop:audio_output_start', self.mute_handler)
        message = Message('recognizer_loop:utterance',
                          {"utterances": [text]},
                          context={'origin': 'Telegram'})
        self.bus.emit(message)

    def response_handler(self, message):
        response = message.data.get("utterance")
        self.bus.emit(Message("telegram-skill:response",
                      {"intent_name": "telegram-response", "utterance": response}))

    def mute_handler(self, message):
        self.mixer.setmute(1)
        wait_while_speaking()
        self.mixer.setmute(0)
        self.remove_event('recognizer_loop:audio_output_start')

    def shutdown(self):
        self.log.info("Shutting down.")
        return True

    def stop(self):
        self.log.info("Stopping...")
        for event in ['recognizer_loop:audio_output_start', 'speak']:
        try:
            self.remove_event(event)
        except:
            pass
        return True


def create_skill():
    return Telegram()
