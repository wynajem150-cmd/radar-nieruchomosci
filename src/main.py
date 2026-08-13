import argparse
import hashlib
import html
import json
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

STATE_FILE = Path("seen.json")
WARSAW = ZoneInfo("Europe/Warsaw")

PRICE_RE = re.compile(r"(?<!\d)(\d{2,3}(?:[ .\u00a0]\d{3})+|\d