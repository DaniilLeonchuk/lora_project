import userid

Token=input('Enter Telegram Token: ')

response=userid.get_updates(Token)
UsId=response['result'][0]['message']['chat']['id']
userid.send_telegram_message(Token, UsId, "Контейнер был вскрыт")