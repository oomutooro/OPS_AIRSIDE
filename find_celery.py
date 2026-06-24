# find_celery.py
import os
import importlib
import sys

def scan_for_celery():
    print("=" * 60)
    print("Scanning for Celery instances...")
    print("=" * 60)
    
    # Scan __init__.py
    try:
        module = importlib.import_module('app')
        print(f"\nLooking in app/__init__.py:")
        for attr in dir(module):
            try:
                obj = getattr(module, attr)
                if 'celery' in str(type(obj)).lower() or attr.lower().startswith('celery'):
                    print(f"  ✓ Found: app.{attr}")
            except:
                pass
    except Exception as e:
        print(f"Error scanning app: {e}")
    
    # Check for celery.py files
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file == 'celery.py' or file.endswith('celery.py'):
                module_path = os.path.join(root, file).replace('\\', '.').replace('./', '').replace('.py', '')
                if module_path.startswith('.'):
                    module_path = module_path[1:]
                print(f"\nFound file: {module_path}")
                
                try:
                    module = importlib.import_module(module_path)
                    for attr in dir(module):
                        if attr == 'app' or attr == 'celery' or attr.startswith('celery'):
                            print(f"  ✓ Found: {module_path}.{attr}")
                except Exception as e:
                    print(f"  Error importing: {e}")
    
    print("\n" + "=" * 60)
    print("Check your app's config for: CELERY_BROKER_URL")
    print("=" * 60)

if __name__ == "__main__":
    scan_for_celery()