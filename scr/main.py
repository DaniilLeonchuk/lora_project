from flask import Flask, render_template, jsonify, request
import sqlite3
from datetime import datetime
import json
import asyncio
import websockets
import calendar
import time
import threading
import schedule
import requests
from functools import wraps

app = Flask(__name__)

# Конфигурация
TOKEN = '7916126911:AAEXs_-9dTaMLXRKZY4-0wUdRFgGl8iTGTY'
SERVER_URL = "ws://10.101.18.28:8002"
LOGIN = "temp"
PASSWORD = "123"
DEVICE_EUI = "3139303459316A0B"

# Пороги для уведомлений (можно настроить)
THRESHOLDS = {
    'temperature_min': -20,
    'temperature_max': 40,
    'humidity_min': 20,
    'humidity_max': 80,
    'battery_min': 20
}

# Кэш для хранения ID чатов Telegram
telegram_chats = set()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('lora.db')
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100),
            sensor_type VARCHAR(50),
            location VARCHAR(200),
            installation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id VARCHAR(50),
            temperature DECIMAL(5,2),
            temperature2 DECIMAL(5,2),
            humidity DECIMAL(5,2),
            door_open BOOLEAN,
            door_open2 BOOLEAN,
            battery_level DECIMAL(5,2),
            rssi INTEGER,
            corner INTEGER,
            low_humidity DECIMAL(5,2),
            up_humidity DECIMAL(5,2),
            low_temperature DECIMAL(5,2),
            up_temperature DECIMAL(5,2),
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            raw_data TEXT
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS workers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100),
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id VARCHAR(50),
            message TEXT,
            notification_type VARCHAR(50),
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Добавляем тестовые устройства
    cur.execute('''
        INSERT OR IGNORE INTO devices (device_id, name, sensor_type, location) 
        VALUES ('TL11_001', 'Датчик температуры ТЛ-11', 'temperature', 'Внутри контейнера')
    ''')
    cur.execute('''
        INSERT OR IGNORE INTO devices (device_id, name, sensor_type, location) 
        VALUES ('HS0101_001', 'Датчик контроля SMART-HS0101', 'multi_sensor', 'Снаружи контейнера')
    ''')
    
    conn.commit()
    conn.close()
    print("База данных инициализирована")

def get_db_connection():
    conn = sqlite3.connect('lora.db')
    conn.row_factory = sqlite3.Row
    return conn

# Функции для работы с Telegram
def get_telegram_updates(token):
    """Получаем обновления от Telegram бота"""
    url = f'https://api.telegram.org/bot{token}/getUpdates'
    try:
        response = requests.get(url, timeout=10)
        response_data = response.json()
        
        if response_data.get('ok'):
            for update in response_data['result']:
                if 'message' in update and 'chat' in update['message']:
                    chat_id = update['message']['chat']['id']
                    telegram_chats.add(chat_id)
                    
                    # Сохраняем в базу данных
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute('''
                        INSERT OR IGNORE INTO workers (telegram_id) 
                        VALUES (?)
                    ''', (str(chat_id),))
                    conn.commit()
                    conn.close()
                    
            return telegram_chats
    except Exception as e:
        print(f"Ошибка при получении обновлений Telegram: {e}")
    return set()

def send_telegram_message(token, chat_id, message):
    """Отправляем сообщение в Telegram"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Telegram: {e}")
        return None

def send_notification_to_all(message):
    """Отправляем уведомление всем подписчикам"""
    get_telegram_updates(TOKEN)  # Обновляем список чатов
    
    for chat_id in telegram_chats:
        send_telegram_message(TOKEN, chat_id, message)
    
    # Логируем уведомление в базе данных
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO notifications (message, notification_type)
        VALUES (?, 'threshold')
    ''', (message,))
    conn.commit()
    conn.close()

# Функции для парсинга данных
def parse_hs0101_data(hex_string):
    """Парсим данные от датчика HS0101"""
    try:
        lenghts = [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]
        result = []
        start = 0
        
        for lent in lenghts:
            if start + lent <= len(hex_string):
                result.append(hex_string[start:start+lent])
                start += lent
            else:
                result.append(hex_string[start:])
        
        packet = result[0].lstrip('0')  # тип пакета
        battery = int(result[1], 16)  # батарея, %
        
        # Время
        time_hex = result[5] + result[4] + result[3] + result[2]
        timestamp = int(time_hex, 16)
        dt_object = datetime.fromtimestamp(timestamp)
        
        # Температура
        temp_hex = result[7] + result[6]
        temperature = int(temp_hex, 16) / 10
        
        # Влажность
        humidity = int(result[8], 16)
        
        # Состояние датчиков открытия
        door_open = int(result[9], 16) == 0  # 0 - открыто
        door_open2 = int(result[10], 16) == 0  # 0 - открыто
        
        # Угол отклонения
        corner = int(result[11], 16)
        
        # Пороги
        low_humidity = int(result[12], 16)
        up_humidity = int(result[13], 16)
        
        low_temperature = int(result[14], 16)
        up_temperature = int(result[15], 16)
        
        # Корректировка отрицательных температур
        if low_temperature >= 128:
            low_temperature = low_temperature - 256
        
        if up_temperature >= 128:
            up_temperature = up_temperature - 256
        
        return {
            'device_type': 'HS0101',
            'packet_type': packet,
            'battery': battery,
            'timestamp': dt_object,
            'temperature': temperature,
            'humidity': humidity,
            'door_open': door_open,
            'door_open2': door_open2,
            'corner': corner,
            'low_humidity': low_humidity,
            'up_humidity': up_humidity,
            'low_temperature': low_temperature,
            'up_temperature': up_temperature,
            'raw_data': hex_string
        }
        
    except Exception as e:
        print(f"Ошибка парсинга HS0101: {e}")
        return None

def parse_tl11_data(hex_string):
    """Парсим данные от датчика TL11"""
    try:
        lenghts = [2, 2, 2, 2, 2, 2, 2, 2, 2, 2]
        result = []
        start = 0
        
        for lent in lenghts:
            if start + lent <= len(hex_string):
                result.append(hex_string[start:start+lent])
                start += lent
            else:
                result.append(hex_string[start:])
        
        battery = int(result[0], 16)  # батарея, %
        
        # Время
        time_hex = result[4] + result[3] + result[2] + result[1]
        timestamp = int(time_hex, 16)
        dt_object = datetime.fromtimestamp(timestamp)
        
        # Температуры
        temp_hex = result[6] + result[5]
        temperature = int(temp_hex, 16) / 10  # температура поддона
        
        temp2_hex = result[8] + result[7]
        temperature2 = int(temp2_hex, 16) / 10  # температура продукта
        
        up_temperature = int(result[9], 16)  # верхний порог
        
        return {
            'device_type': 'TL11',
            'battery': battery,
            'timestamp': dt_object,
            'temperature': temperature,
            'temperature2': temperature2,
            'up_temperature': up_temperature,
            'raw_data': hex_string
        }
        
    except Exception as e:
        print(f"Ошибка парсинга TL11: {e}")
        return None

# Проверка порогов и отправка уведомлений
def check_thresholds_and_notify(device_id, data):
    """Проверяем данные на превышение порогов и отправляем уведомления"""
    messages = []
    
    # Проверка температуры
    if 'temperature' in data:
        temp = data['temperature']
        if temp < THRESHOLDS['temperature_min']:
            messages.append(f"⚠️ <b>ВНИМАНИЕ!</b>\n"
                          f"Устройство: {device_id}\n"
                          f"Температура ниже порога: {temp}°C < {THRESHOLDS['temperature_min']}°C")
        
        elif temp > THRESHOLDS['temperature_max']:
            messages.append(f"⚠️ <b>ВНИМАНИЕ!</b>\n"
                          f"Устройство: {device_id}\n"
                          f"Температура выше порога: {temp}°C > {THRESHOLDS['temperature_max']}°C")
    
    # Проверка влажности
    if 'humidity' in data:
        humid = data['humidity']
        if humid < THRESHOLDS['humidity_min']:
            messages.append(f"⚠️ <b>ВНИМАНИЕ!</b>\n"
                          f"Устройство: {device_id}\n"
                          f"Влажность ниже порога: {humid}% < {THRESHOLDS['humidity_min']}%")
        
        elif humid > THRESHOLDS['humidity_max']:
            messages.append(f"⚠️ <b>ВНИМАНИЕ!</b>\n"
                          f"Устройство: {device_id}\n"
                          f"Влажность выше порога: {humid}% > {THRESHOLDS['humidity_max']}%")
    
    # Проверка батареи
    if 'battery' in data and data['battery'] < THRESHOLDS['battery_min']:
        messages.append(f"🔋 <b>Низкий заряд батареи!</b>\n"
                       f"Устройство: {device_id}\n"
                       f"Заряд: {data['battery']}% < {THRESHOLDS['battery_min']}%")
    
    # Проверка открытия дверей
    if data.get('door_open'):
        messages.append(f"🚨 <b>ДВЕРЬ ОТКРЫТА!</b>\n"
                       f"Устройство: {device_id}\n"
                       f"Время: {data['timestamp']}")
    
    if data.get('door_open2'):
        messages.append(f"🚨 <b>ВТОРАЯ ДВЕРЬ ОТКРЫТА!</b>\n"
                       f"Устройство: {device_id}\n"
                       f"Время: {data['timestamp']}")
    
    # Отправляем все уведомления
    for message in messages:
        print(f"Отправка уведомления: {message}")
        send_notification_to_all(message)
    
    return len(messages) > 0

# Сохранение данных в базу
def save_measurement(device_id, parsed_data):
    """Сохраняем данные в базу данных"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if parsed_data['device_type'] == 'HS0101':
            cur.execute('''
                INSERT INTO measurements 
                (device_id, temperature, humidity, door_open, door_open2, 
                 battery_level, corner, low_humidity, up_humidity, 
                 low_temperature, up_temperature, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (device_id, parsed_data['temperature'], parsed_data['humidity'],
                  parsed_data['door_open'], parsed_data['door_open2'],
                  parsed_data['battery'], parsed_data['corner'],
                  parsed_data['low_humidity'], parsed_data['up_humidity'],
                  parsed_data['low_temperature'], parsed_data['up_temperature'],
                  parsed_data['raw_data']))
        
        elif parsed_data['device_type'] == 'TL11':
            cur.execute('''
                INSERT INTO measurements 
                (device_id, temperature, temperature2, battery_level, raw_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (device_id, parsed_data['temperature'], 
                  parsed_data['temperature2'], parsed_data['battery'],
                  parsed_data['raw_data']))
        
        conn.commit()
        print(f"Данные устройства {device_id} сохранены в базу")
        
        # Проверяем пороги
        check_thresholds_and_notify(device_id, parsed_data)
        
    except Exception as e:
        print(f"Ошибка при сохранении данных: {e}")
        conn.rollback()
    finally:
        conn.close()

# Асинхронное получение данных с IoT сервера
async def fetch_iot_data_async():
    """Асинхронная функция для получения данных с IoT сервера"""
    try:
        async with websockets.connect(SERVER_URL, open_timeout=30) as websocket:
            print(f"Подключено к серверу {SERVER_URL}")

            # 1. Авторизация
            auth_request = {
                "cmd": "auth_req",
                "login": LOGIN,
                "password": PASSWORD
            }
            await websocket.send(json.dumps(auth_request))
            auth_response = await websocket.recv()
            auth_data = json.loads(auth_response)

            if auth_data.get("status") is True and "token" in auth_data:
                token = auth_data["token"]
                print(f"Авторизация успешна. Получен токен: {token}")

                # 2. Запрос данных
                data_request = {
                    "cmd": "get_data_req",
                    "devEui": DEVICE_EUI,
                    "direction": "UPLINK",
                    "select": {
                        "date_from": calendar.timegm(time.strptime('2025-04-12 15:00:00', '%Y-%m-%d %H:%M:%S'))
                    }
                }
                await websocket.send(json.dumps(data_request))
                
                # 3. Получение и обработка ответа
                while True:
                    response = await websocket.recv()
                    data = json.loads(response)
                    
                    if data.get("cmd") == "get_data_resp":
                        print("Получены данные устройства")
                        
                        # Обработка данных
                        if "data_list" in data:
                            for item in data["data_list"]:
                                if "data" in item:
                                    hex_data = item["data"]
                                    device_id = item.get("devEui", DEVICE_EUI)
                                    
                                    # Определяем тип устройства и парсим данные
                                    if len(hex_data) == 32:  # HS0101
                                        parsed = parse_hs0101_data(hex_data)
                                        if parsed:
                                            save_measurement("HS0101_001", parsed)
                                    elif len(hex_data) == 20:  # TL11
                                        parsed = parse_tl11_data(hex_data)
                                        if parsed:
                                            save_measurement("TL11_001", parsed)
                        
                        break
                    elif data.get("status") is False:
                        print(f"Ошибка при запросе данных: {data.get('err_string')}")
                        break

            else:
                print(f"Ошибка авторизации: {auth_data.get('err_string', 'Неизвестная ошибка')}")

    except Exception as e:
        print(f"Ошибка при получении данных: {e}")

def fetch_iot_data_sync():
    """Синхронная обертка для асинхронной функции"""
    try:
        # Создаем новый event loop для каждого вызова
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(fetch_iot_data_async())
        loop.close()
    except Exception as e:
        print(f"Ошибка в синхронной обертке: {e}")

# Фоновая задача для получения данных
def background_fetch():
    """Фоновая задача для регулярного получения данных"""
    while True:
        try:
            fetch_iot_data_sync()
            # Ждем 60 секунд перед следующим запросом
            time.sleep(60)
        except Exception as e:
            print(f"Ошибка в фоновой задаче: {e}")
            time.sleep(10)

# Маршруты Flask
@app.route('/')
def index():
    conn = get_db_connection()
    devices = conn.execute('SELECT * FROM devices').fetchall()
    
    devices_with_data = []
    for device in devices:
        last_measurement = conn.execute(
            'SELECT * FROM measurements WHERE device_id = ? ORDER BY id DESC LIMIT 1',
            (device['device_id'],)
        ).fetchone()
        devices_with_data.append((device, last_measurement))
    
    conn.close()
    return render_template('index.html', devices_with_data=devices_with_data)

@app.route('/device/<device_id>')
def device_detail(device_id):
    conn = get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    measurements = conn.execute(
        'SELECT * FROM measurements WHERE device_id = ? ORDER BY received_at DESC LIMIT 50',
        (device_id,)
    ).fetchall()
    conn.close()
    return render_template('device.html', device=device, measurements=measurements)

@app.route('/api/sensor_data', methods=['POST'])
def receive_sensor_data():
    """Эндпоинт для приема данных напрямую от устройств"""
    try:
        data = request.json
        
        # Определяем тип устройства по данным
        hex_data = data.get('data', '')
        device_id = data.get('device_id', 'unknown')
        
        if len(hex_data) == 32:  # HS0101
            parsed = parse_hs0101_data(hex_data)
            if parsed:
                save_measurement(device_id, parsed)
        elif len(hex_data) == 20:  # TL11
            parsed = parse_tl11_data(hex_data)
            if parsed:
                save_measurement(device_id, parsed)
        else:
            # Сохраняем как сырые данные
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO measurements (device_id, raw_data)
                VALUES (?, ?)
            ''', (device_id, hex_data))
            conn.commit()
            conn.close()
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        print(f"Ошибка при обработке данных: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/device/<device_id>')
def api_device_data(device_id):
    """API для получения данных устройства"""
    conn = get_db_connection()
    measurements = conn.execute('''
        SELECT temperature, humidity, door_open, battery_level, rssi, received_at 
        FROM measurements WHERE device_id = ? ORDER BY received_at DESC LIMIT 100
    ''', (device_id,)).fetchall()
    conn.close()
    data = [dict(row) for row in measurements]
    return jsonify(data)

@app.route('/api/fetch_data')
def api_fetch_data():
    """Ручной запуск получения данных (синхронная версия)"""
    try:
        # Запускаем в отдельном потоке, чтобы не блокировать ответ Flask
        import threading
        thread = threading.Thread(target=fetch_iot_data_sync, daemon=True)
        thread.start()
        return jsonify({'status': 'fetching', 'message': 'Запрос данных запущен в фоне'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/send_test_notification')
def api_send_test_notification():
    """Отправка тестового уведомления"""
    message = "🔔 <b>Тестовое уведомление</b>\nЭто тестовое сообщение от системы мониторинга."
    send_notification_to_all(message)
    return jsonify({'status': 'test_notification_sent'})

@app.route('/api/thresholds', methods=['GET', 'POST'])
def api_thresholds():
    """Управление порогами"""
    if request.method == 'POST':
        data = request.json
        for key, value in data.items():
            if key in THRESHOLDS:
                THRESHOLDS[key] = value
        return jsonify({'status': 'updated', 'thresholds': THRESHOLDS})
    
    return jsonify(THRESHOLDS)

# Запуск фоновой задачи
def start_background_tasks():
    """Запускаем фоновые задачи в отдельном потоке"""
    thread = threading.Thread(target=background_fetch, daemon=True)
    thread.start()
    print("Фоновая задача для получения данных запущена")

if __name__ == '__main__':
    # Инициализация
    init_db()
    
    # Получаем начальные данные о чатах Telegram
    get_telegram_updates(TOKEN)
    
    # Запускаем фоновую задачу
    start_background_tasks()
    
    # Запускаем Flask сервер
    app.run(debug=True, host='0.0.0.0', port=5000)