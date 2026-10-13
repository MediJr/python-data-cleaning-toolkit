"""Allow ``python -m data_cleaning``."""

import sys

from .cli import main

sys.exit(main())
