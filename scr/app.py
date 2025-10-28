from flask import Flask, request, jsonify
import psycopg2
import os
from datetime import datetime

DB_CONFIG = [
    'host': 'localhost',
    'database': 'lora_monitoring',
    'user': 'lora_user',
    'password': 'lora_password',
    'port': 5432
]

