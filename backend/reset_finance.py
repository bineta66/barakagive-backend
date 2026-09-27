import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

tables = [
    'finance_justification',
    'finance_depense',
    'finance_don',
    'finance_budget'
]

with connection.cursor() as cursor:
    for table in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            print(f"Dropped table {table}")
        except Exception as e:
            print(f"Could not drop {table}: {e}")
    
    # Remove migration history
    try:
        cursor.execute("DELETE FROM django_migrations WHERE app = 'finance';")
        print("Cleared finance migration history")
    except Exception as e:
        print(f"Could not clear migration history: {e}")
