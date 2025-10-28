from flask import Flask, request, jsonify
import psycopg2
import os
from datetime import datetime

app = Flask(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'database': 'lora_monitoring',
    'user': 'lora_user',
    'password': 'lora_password',
    'port': 5432
}

@app.route('/')
def rout():
    return 'Hello'


if __name__ == '__main__':
    app.run(debug=True)