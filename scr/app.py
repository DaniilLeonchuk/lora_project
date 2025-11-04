from flask import Flask, render_template, jsonify, request
import sqlite3
from datetime import datetime

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('lora.db')
    cur = conn.cursor()
    
    # Таблица устройств
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
    
    # Таблица измерений
    cur.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id VARCHAR(50),
            temperature DECIMAL(5,2),
            humidity DECIMAL(5,2),
            door_open BOOLEAN,
            battery_level DECIMAL(5,2),
            rssi INTEGER,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Реальные датчики
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

def get_db_connection():
    conn = sqlite3.connect('lora.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    
    # Получаем устройства
    devices = conn.execute('SELECT * FROM devices').fetchall()
    
    # Получаем последние данные для каждого устройства
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
    
    device = conn.execute(
        'SELECT * FROM devices WHERE device_id = ?', (device_id,)
    ).fetchone()
    
    measurements = conn.execute(
        'SELECT * FROM measurements WHERE device_id = ? ORDER BY received_at DESC LIMIT 50',
        (device_id,)
    ).fetchall()
    
    conn.close()
    
    return render_template('device.html', device=device, measurements=measurements)

# API для приема данных с датчиков
@app.route('/api/sensor_data', methods=['POST'])
def receive_sensor_data():
    """Основной API для приема данных с датчиков"""
    try:
        data = request.json
        
        conn = get_db_connection()
        
        # Сохраняем измерение
        conn.execute('''
            INSERT INTO measurements 
            (device_id, temperature, humidity, door_open, battery_level, rssi)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['device_id'], data.get('temperature'), data.get('humidity'),
              data.get('door_open', False), data.get('battery', 100), 
              data.get('rssi', -70)))
        
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# API для получения данных устройства
@app.route('/api/device/<device_id>')
def api_device_data(device_id):
    conn = get_db_connection()
    
    measurements = conn.execute('''
        SELECT temperature, humidity, door_open, battery_level, rssi, received_at 
        FROM measurements 
        WHERE device_id = ? 
        ORDER BY received_at DESC LIMIT 100
    ''', (device_id,)).fetchall()
    
    conn.close()
    
    data = [dict(row) for row in measurements]
    return jsonify(data)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)