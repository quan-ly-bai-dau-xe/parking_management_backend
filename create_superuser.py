import os
import sys
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.append('/e/parking_management_backend')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

# Create superuser
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='admin123'
    )
    print('Superuser created successfully.')
else:
    print('Superuser already exists.')