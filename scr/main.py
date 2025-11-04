from flask import Flask
import sqlite3
import os

app = Flask(__name__)

# Инициализация базы
def init_db():
    conn = sqlite3.connect('lora.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS test_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute("INSERT OR IGNORE INTO test_table (name) VALUES ('SQLite test record')")
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('lora.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM test_table')
    records = cur.fetchall()
    conn.close()
    
    result = "<h1>Данные из SQLite:</h1><ul>"
    for record in records:
        result += f"<li>ID: {record[0]}, Name: {record[1]}, Created: {record[2]}</li>"
    result += "</ul>"
    return result

@app.route('/add/<name>')
def add_record(name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO test_table (name) VALUES (?)', (name,))
    conn.commit()
    conn.close()
    return f"✅ Запись '{name}' добавлена"

if __name__ == '__main__':
    init_db()
    app.run(debug=True)