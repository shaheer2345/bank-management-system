#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.management import call_command

# Run all tests
try:
    call_command('test', 'banking', verbosity=2)
    print("\n✓ All tests passed successfully!")
except SystemExit as e:
    if e.code != 0:
        print("\n✗ Some tests failed")
        sys.exit(1)
