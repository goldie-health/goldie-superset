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

# Dedicated Redis logical DBs per concern so they never collide on keyspace.
# (Previously the SQL Lab results backend shared db 0 with the Celery broker,
# and the data cache shared db 1 with the Celery result backend.)
REDIS_CELERY_DB = os.getenv("REDIS_CELERY_DB", "0")          # Celery broker
REDIS_RESULTS_DB = os.getenv("REDIS_RESULTS_DB", "1")        # Celery result backend
REDIS_RATELIMIT_DB = os.getenv("REDIS_RATELIMIT_DB", "2")    # Flask-Limiter
REDIS_DATA_CACHE_DB = os.getenv("REDIS_DATA_CACHE_DB", "3")  # chart/data + thumbnail cache
REDIS_SQLLAB_DB = os.getenv("REDIS_SQLLAB_DB", "4")          # SQL Lab results backend
REDIS_STATE_CACHE_DB = os.getenv("REDIS_STATE_CACHE_DB", "5")  # filter/explore state
REDIS_ASYNC_DB = os.getenv("REDIS_ASYNC_DB", "6")           # global async query events

# Default cache TTLs (seconds). Data cache is long because analytics data
# refreshes infrequently; pair it with scheduled cache warmup for best effect.
APP_CACHE_TIMEOUT = int(os.getenv("APP_CACHE_TIMEOUT", "300"))
DATA_CACHE_TIMEOUT = int(os.getenv("DATA_CACHE_TIMEOUT", "86400"))

# RESULTS_BACKEND = FileSystemCache("/app/superset_home/sqllab")
RESULTS_BACKEND = RedisCache(
    host=REDIS_HOST,
    port=int(REDIS_PORT),
    db=int(REDIS_SQLLAB_DB),
    key_prefix="superset_results",
)

# Generic Flask app cache (metadata, misc). Short TTL is fine here.
CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": APP_CACHE_TIMEOUT,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_HOST": REDIS_HOST,
    "CACHE_REDIS_PORT": REDIS_PORT,
    "CACHE_REDIS_DB": REDIS_DATA_CACHE_DB,
}

# Chart/query result cache — the one that actually offloads the analytics DB.
DATA_CACHE_CONFIG = {
    **CACHE_CONFIG,
    "CACHE_DEFAULT_TIMEOUT": DATA_CACHE_TIMEOUT,
    "CACHE_KEY_PREFIX": "superset_data_",
}
THUMBNAIL_CACHE_CONFIG = {
    **CACHE_CONFIG,
    "CACHE_DEFAULT_TIMEOUT": DATA_CACHE_TIMEOUT,
    "CACHE_KEY_PREFIX": "superset_thumb_",
}

# Filter and explore form state — default backend is the metadata DB
# (SupersetMetastoreCache), which adds load to the metadata pool. Move it to
# Redis to keep that pool free. Trade-off: state is lost if Redis is flushed.
FILTER_STATE_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": int(os.getenv("FILTER_STATE_CACHE_TIMEOUT", "604800")),
    "CACHE_KEY_PREFIX": "superset_filter_",
    "CACHE_REDIS_HOST": REDIS_HOST,
    "CACHE_REDIS_PORT": REDIS_PORT,
    "CACHE_REDIS_DB": REDIS_STATE_CACHE_DB,
    "REFRESH_TIMEOUT_ON_RETRIEVAL": True,
}
EXPLORE_FORM_DATA_CACHE_CONFIG = {
    **FILTER_STATE_CACHE_CONFIG,
    "CACHE_KEY_PREFIX": "superset_explore_",
}

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

    # Run chart/dashboard queries asynchronously on Celery workers instead of
    # tying up a web worker thread + DB connection for the whole query. This is
    # the key fix for dashboards with many charts exhausting the connection pool.
    'GLOBAL_ASYNC_QUERIES': os.getenv(
        "GLOBAL_ASYNC_QUERIES", "true"
    ).lower() == "true",
}

# ============================================================================
# Global Async Queries
# ============================================================================
# Uses the "polling" transport so no extra superset-websocket service is
# required — the browser polls the Superset API, results are streamed via Redis,
# and the actual queries run on the existing Celery workers.
GLOBAL_ASYNC_QUERIES_TRANSPORT = "polling"
# Secret used to sign the async JWT cookie. MUST not be the upstream default;
# fall back to the app SECRET_KEY if a dedicated one isn't provided.
GLOBAL_ASYNC_QUERIES_JWT_SECRET = os.getenv(
    "GLOBAL_ASYNC_QUERIES_JWT_SECRET", SECRET_KEY
)
GLOBAL_ASYNC_QUERIES_JWT_COOKIE_SECURE = SESSION_COOKIE_SECURE
GLOBAL_ASYNC_QUERIES_CACHE_BACKEND = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_HOST": REDIS_HOST,
    "CACHE_REDIS_PORT": int(REDIS_PORT),
    "CACHE_REDIS_DB": int(REDIS_ASYNC_DB),
    "CACHE_DEFAULT_TIMEOUT": 300,
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
# Metadata database connection pool + SQL Debugging Configuration
# ============================================================================

# SQL echo logs EVERY statement run against the metadata DB. It is a heavy
# perf hit and must stay OFF in production. Enable only for local debugging
# via SQLALCHEMY_ECHO=true.
SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"

# Connection pool tuning for the metadata database (the RDS Postgres that
# backs Superset itself). Defaults below are sized for the gunicorn worker x
# thread count in docker/entrypoints/run-server.sh. Keep
# (workers * threads) <= (pool_size + max_overflow) <= RDS max_connections.
SQLALCHEMY_ENGINE_OPTIONS = {
    "echo": SQLALCHEMY_ECHO,
    "pool_size": int(os.getenv("SQLALCHEMY_POOL_SIZE", "20")),
    "max_overflow": int(os.getenv("SQLALCHEMY_MAX_OVERFLOW", "40")),
    "pool_timeout": int(os.getenv("SQLALCHEMY_POOL_TIMEOUT", "60")),
    "pool_recycle": int(os.getenv("SQLALCHEMY_POOL_RECYCLE", "1800")),
    "pool_pre_ping": True,
}

# Engine/pool logging. Only emit per-query INFO logs when debugging.
logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if SQLALCHEMY_ECHO else logging.WARNING
)
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

# Logs every external (chart / SQL Lab) query to the console. Useful for
# debugging, but pure overhead in production — gate it behind the same flag.
if SQLALCHEMY_ECHO:
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
