# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
# This file is included in the final Docker image and SHOULD be overridden when
# deploying the image to prod. Settings configured here are intended for use in local
# development environments. Also note that superset_config_docker.py is imported
# as a final step as a means to override "defaults" configured here
#
import logging
import os
import sys

from celery.schedules import crontab
# from flask_caching.backends.filesystemcache import FileSystemCache
from flask_caching.backends.rediscache import RedisCache

logger = logging.getLogger()

SECRET_KEY = os.getenv("SUPERSET_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "TEST_NON_DEV_SECRET":
    raise ValueError(
        "SECRET_KEY must be set via SUPERSET_SECRET_KEY environment variable "
        "for production deployments. Generate with: openssl rand -base64 42"
    )


DATABASE_DIALECT = os.getenv("DATABASE_DIALECT")
DATABASE_USER = os.getenv("DATABASE_USER")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")
DATABASE_DB = os.getenv("DATABASE_DB")

# Validate required database environment variables
required_db_vars = [
    "DATABASE_DIALECT",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_DB",
]
missing_vars = [var for var in required_db_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required database environment variables: {', '.join(missing_vars)}")

# The SQLAlchemy connection string.
SQLALCHEMY_DATABASE_URI = (
    f"{DATABASE_DIALECT}://"
    f"{DATABASE_USER}:{DATABASE_PASSWORD}@"
    f"{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_DB}"
)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
# REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_CELERY_DB = os.getenv("REDIS_CELERY_DB", "0")
REDIS_RESULTS_DB = os.getenv("REDIS_RESULTS_DB", "1")
REDIS_RATELIMIT_DB = os.getenv("REDIS_RATELIMIT_DB", "2")

# RESULTS_BACKEND = FileSystemCache("/app/superset_home/sqllab")
RESULTS_BACKEND = RedisCache(
    host=REDIS_HOST,
    port=int(REDIS_PORT),
    key_prefix="superset_results",
)

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_HOST": REDIS_HOST,
    "CACHE_REDIS_PORT": REDIS_PORT,
    "CACHE_REDIS_DB": REDIS_RESULTS_DB,
}
DATA_CACHE_CONFIG = CACHE_CONFIG
THUMBNAIL_CACHE_CONFIG = CACHE_CONFIG

# Flask-Limiter storage backend (Redis)
# This prevents the warning about in-memory storage and enables proper rate limiting
RATELIMIT_STORAGE_URI = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_RATELIMIT_DB}"

class CeleryConfig:
    broker_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_CELERY_DB}"
    imports = (
        "superset.sql_lab",
        "superset.tasks.scheduler",
        "superset.tasks.thumbnails",
        "superset.tasks.cache",
    )
    result_backend = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_RESULTS_DB}"
    worker_prefetch_multiplier = 1
    task_acks_late = False
    beat_schedule = {
        "reports.scheduler": {
            "task": "reports.scheduler",
            "schedule": crontab(minute="*", hour="*"),
        },
        "reports.prune_log": {
            "task": "reports.prune_log",
            "schedule": crontab(minute=10, hour=0),
        },
    }


CELERY_CONFIG = CeleryConfig

GUEST_ROLE_NAME = "Carenet"
# PUBLIC_ROLE_LIKE = "Public"
GUEST_TOKEN_JWT_AUDIENCE = "superset"

FEATURE_FLAGS = {
    # Enabling Embedding via the SDK
    'EMBEDDED_SUPERSET': True,

    # Manage access to Dashboards
    'DASHBOARD_RBAC': True,

    # Jinja templating in queries for SQL Lab and Explore
    'ENABLE_TEMPLATE_PROCESSING': True,
}

ALERT_REPORTS_NOTIFICATION_DRY_RUN = False
WEBDRIVER_BASEURL = f"http://superset_app{os.environ.get('SUPERSET_APP_ROOT', '/')}/"  # When using docker compose baseurl should be http://superset_nginx{ENV{BASEPATH}}/  # noqa: E501
# The base URL for the email report hyperlinks.
WEBDRIVER_BASEURL_USER_FRIENDLY = (
    f"http://localhost:8888/{os.environ.get('SUPERSET_APP_ROOT', '/')}/"
)
SQLLAB_CTAS_NO_LIMIT = False

# Session security - MUST be True in production if using HTTPS
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
SESSION_COOKIE_HTTPONLY = True

SESSION_COOKIE_SAMESITE = None

log_level_text = os.getenv("SUPERSET_LOG_LEVEL", "INFO")
LOG_LEVEL = getattr(logging, log_level_text.upper(), logging.INFO)

# ============================================================================
# SQL Debugging Configuration
# ============================================================================

# Enable SQL query logging to console
# This will log all SQL queries executed by SQLAlchemy (metadata database)
SQLALCHEMY_ENGINE_OPTIONS = {
    "echo": True,  # Log all SQL statements
}

# Enable logging for SQLAlchemy engine to see SQL queries in console
# Set to logging.INFO to see SQL queries, or logging.DEBUG for more details
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

# Custom QUERY_LOGGER to log all SQL queries to external databases
# This will log queries from SQL Lab, charts, and dashboards
def log_sql_query(
    database_uri,
    query,
    schema=None,
    client=None,
    security_manager=None,
    log_params=None,
):
    """Log SQL queries to console for debugging"""
    # Mask password in database URI for security
    masked_uri = database_uri
    if "@" in database_uri:
        parts = database_uri.split("@")
        if "://" in parts[0]:
            protocol_user = parts[0].split("://")
            if len(protocol_user) == 2:
                protocol = protocol_user[0]
                user_pass = protocol_user[1]
                if ":" in user_pass:
                    user = user_pass.split(":")[0]
                    masked_uri = f"{protocol}://{user}:***@{parts[1]}"
    
    schema_info = f" schema={schema}" if schema else ""
    logger.info(
        f"[SQL QUERY]{schema_info}\n"
        f"Database: {masked_uri}\n"
        f"Query:\n{query}\n"
        f"{'=' * 80}"
    )

QUERY_LOGGER = log_sql_query

# ============================================================================
# Talisman Security Configuration
# ============================================================================
# Enable Talisman for Content Security Policy
TALISMAN_ENABLED = os.getenv("TALISMAN_ENABLED", "true").lower() == "true"

ENABLE_CORS = True
CORS_OPTIONS = {
    "supports_credentials": False,
    "origins": [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://*.goldiehealth.com",
    ],
}

HTTP_HEADERS = {
    "X-Frame-Options": "ALLOWALL",
}

# Production Talisman config - adjust CSP as needed for your deployment
TALISMAN_CONFIG = {
    "content_security_policy": {
        "base-uri": ["'self'"],
        "default-src": ["'self'"],
        "img-src": [
            "'self'",
            "blob:",
            "data:",
            "https://apachesuperset.gateway.scarf.sh",
            "https://static.scarf.sh/",
            "ows.terrestris.de",
            "https://cdn.document360.io",
        ],
        "worker-src": ["'self'", "blob:"],
        "connect-src": [
            "'self'",
            "https://api.mapbox.com",
            "https://events.mapbox.com",
            "https://tile.openstreetmap.org",
            "https://tile.osm.ch",
        ],
        "object-src": "'none'",
        "style-src": ["'self'", "'unsafe-inline'"],
        "script-src": ["'self'", "'strict-dynamic'"],
        "frame-ancestors": [
            "http://localhost:5173",
            "*.goldiehealth.com",
        ]
    },
    "content_security_policy_nonce_in": ["script-src"],
    # Set force_https based on your deployment
    # If you have HTTPS at load balancer level, set to False
    "force_https": os.getenv("TALISMAN_FORCE_HTTPS", "false").lower() == "true",
    "session_cookie_secure": SESSION_COOKIE_SECURE,
    "frame_options": None,
}

# WTF_CSRF_ENABLED = False


WTF_CSRF_EXEMPT_LIST = [
    'superset.security.api.guest_token',
]

# Enable UI-based theme administration for admins
ENABLE_UI_THEME_ADMINISTRATION = True

# Optional: Set initial default themes via configuration
# These can be overridden via the UI when ENABLE_UI_THEME_ADMINISTRATION = True
THEME_DEFAULT = {
    "algorithm": "light"
}

# Hack to force light theme
# TODO: Remove this when we have a proper using of the light theme for embedding
THEME_DARK = {
    "algorithm": "light"
}

if os.getenv("CYPRESS_CONFIG") == "true":
    # When running the service as a cypress backend, we need to import the config
    # located @ tests/integration_tests/superset_test_config.py
    base_dir = os.path.dirname(__file__)
    module_folder = os.path.abspath(
        os.path.join(base_dir, "../../tests/integration_tests/")
    )
    sys.path.insert(0, module_folder)
    from superset_test_config import *  # noqa

    sys.path.pop(0)

#
# Optionally import superset_config_docker.py (which will have been included on
# the PYTHONPATH) in order to allow for local settings to be overridden
#
try:
    import superset_config_docker
    from superset_config_docker import *  # noqa: F403

    logger.info(
        f"Loaded your Docker configuration at [{superset_config_docker.__file__}]"
    )
except ImportError:
    logger.info("Using default Docker config...")
