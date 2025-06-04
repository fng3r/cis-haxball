"""
This is a patch for django-notifications-hq to fix compatibility issues with newer Django versions.
"""

import os
import sys

# Get the path to the notifications package
notifications_path = None
for path in sys.path:
    if os.path.exists(os.path.join(path, 'notifications')):
        notifications_path = os.path.join(path, 'notifications')
        break

if not notifications_path:
    print("Could not find notifications package")
    sys.exit(1)

# Fix the base models.py file
base_models_path = os.path.join(notifications_path, 'base', 'models.py')
if os.path.exists(base_models_path):
    with open(base_models_path, 'r') as f:
        content = f.read()
    
    # Replace index_together with indexes
    content = content.replace(
        "        index_together = ('recipient', 'unread')",
        "        indexes = [models.Index(fields=['recipient', 'unread'])]"
    )
    
    with open(base_models_path, 'w') as f:
        f.write(content)
    
    print(f"Patched {base_models_path}")
else:
    print(f"Could not find {base_models_path}")

print("Patch completed") 