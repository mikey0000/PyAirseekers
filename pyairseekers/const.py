"""Base URLs, timeouts, wire codes, endpoint paths and enum lookups."""

API_BASE_URL = "https://cloud-eu.airseekers-robotics.com"
# Sent as the app does; the server has not been seen to require it (Q4)
APP_VERSION = "1.7.8(2026092001)"

REQUEST_TIMEOUT_S = 20
WHEP_TIMEOUT_S = 15
# How often a viewer calls live/heartbeat: the app was seen 38 s apart, so stay well inside that (Q12)
LIVE_HEARTBEAT_INTERVAL_S = 20

SUCCESS_CODE = 0
# Non-success codes that mean "nothing to report" on one endpoint (D6)
CODE_ALREADY_LATEST = 407
CODE_NO_EXTENDED_WARRANTY = 701
# A non-success envelope whose msg contains one of these is an auth failure
AUTH_ERROR_KEYWORDS = ("illegal", "credential", "token", "unauthorized", "login")

API_SERVER_HOST = "/api/web/server-host"
API_LOGIN = "/user/login"
API_REFRESH_TOKEN = "/api/web/user/refresh-token"
API_IS_AUTHORIZED = "/api/web/user/is-authorized"
API_IOT_CERT = "/api/web/device/iot-cert"

API_DEVICES = "/api/web/device"
API_DEVICE_BIND = "/api/web/device/bind"
API_DEVICE_UNBIND = "/api/web/device/unbind"
API_DEVICE_LOCK = "/api/web/device/lock"
API_DEVICE_UNLOCK = "/api/web/device/unlock"
API_FULL_STATUS = "/api/web/device/full-status"
API_CONFIG = "/api/web/device/config"
API_DEVICE_MAP = "/api/web/device/map"
API_DEVICE_MAP_V2 = "/api/web/device/map/v2"
API_MAP_GEO_DATA = "/api/web/device/map/geo-data"
API_MAP_SWITCH = "/api/web/device/map/switch"
API_EXPLORE_MAP_LATEST = "/api/web/device/explore-map/latest"
API_MAINTENANCE_LIST = "/api/web/device/maintenance/list"
API_SIM_ACTIVATION_STATUS = "/api/web/device/sim/activation-status"
API_SIM_PACKAGE_INFO = "/api/web/device/sim/package-info"
API_NOTIFY_LIST = "/api/web/device/notify/list"
API_RTK_INFO = "/api/web/device/rtk/address-info"
API_RTK_REBOOT = "/api/web/device/rtk-reboot"
API_CLEAN_WARN = "/api/web/device/clean-warn"
API_FILL_LIGHT = "/api/web/device/fill-light-setting"
API_WARRANTY = "/api/web/device/warranty/info"
API_EXTENDED_WARRANTY = "/api/web/device/extended-warranty/info"
API_NRTK_SUPPORTED = "/api/web/device/nrtk-supported"

API_TASK = "/api/web/device/task"
API_TASK_LATEST = "/api/web/device/task/latest"
API_TASK_START = "/api/web/device/task/start"
API_TASK_STOP = "/api/web/device/task/stop"
API_TASK_PAUSE = "/api/web/device/task/pause"
API_TASK_RESUME = "/api/web/device/task/resume"
API_TASK_DOCK = "/api/web/device/task/dock"
API_TASK_RECORD_LATEST = "/api/web/device/task-record/latest"
API_TASK_RECORD_LIST = "/api/web/device/task-record/list"

API_FIRMWARE_LATEST = "/api/web/firmware/latest"
API_FIRMWARE_UPGRADE = "/api/web/firmware/upgrade"
API_VOICE_VERSION = "/api/web/voice-version/latest"

API_LIVE_OPEN = "/api/web/live/open"
API_LIVE_HEARTBEAT = "/api/web/live/heartbeat"
API_LIVE_CAMERA_PARAMS = "/api/web/live/camera-params"
API_LIVE_MOVE_CONTROL = "/api/web/live/move-control"

# Camera indices accepted by /api/web/live/open (confirmed by the owner of a Tron)
CAMERA_FRONT = 1
CAMERA_LEFT = 2
CAMERA_RIGHT = 3
CAMERA_IDS = (CAMERA_FRONT, CAMERA_LEFT, CAMERA_RIGHT)

# Task-level mowing mode
TASK_MODE_LOOKUP = {"global": 0, "ai": 1, "edge": 2, "area": 3}
# Per-zone (task_unit) settings
CUT_SPEED_LOOKUP = {"slow": 1, "normal": 2, "fast": 3}
# "Mowing efficiency" in the app
STRATEGY_LOOKUP = {"stability": 1, "dense": 2, "spare": 3}
# "Turning method" in the app (API field is spelled "truning_mode")
TURNING_MODE_LOOKUP = {"fishtail": 1, "circular": 2, "turn_in_place": 3}

# Map feature `properties.type` for a mowable zone polygon
MAP_FEATURE_KIND_MOWABLE_POLYGON = 1

# Cut height accepted by the task API; the app slider is 30-90 in steps of 10
CUT_HEIGHT_MIN_MM = 20
CUT_HEIGHT_MAX_MM = 120
