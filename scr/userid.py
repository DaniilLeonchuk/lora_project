import requests

def get_updates(token):
    url = f'https://api.telegram.org/bot{token}/getUpdates'
    response = requests.get(url)
    return response.json()


def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=payload)
    return response.json()
