import requests

def get_updates(token):
    url = f'https://api.telegram.org/bot{token}/getUpdates'
    response = requests.get(url)
    response=response.json()
    seen_chat_ids = set()
    for update in response['result']:
        chat_id = update['message']['chat']['id']
        if chat_id not in seen_chat_ids:
            seen_chat_ids.add(chat_id)
    return seen_chat_ids

def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=payload)
    return response.json()
