"""Idempotent bootstrap for the observability stack.

Run with one or more targets: elastic, kibana, grafana, graylog.
Creates least-privilege service accounts, the log index template and ILM
policy, the Kibana data view, a Grafana viewer user and Graylog inputs.
Standard library only so it can run in a stock python image.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

ES = os.environ.get("ES_URL", "http://elasticsearch:9200")
KIBANA = os.environ.get("KIBANA_URL", "http://kibana:5601")
GRAFANA = os.environ.get("GRAFANA_URL", "http://grafana:3000")
GRAYLOG = os.environ.get("GRAYLOG_URL", "http://graylog:9000")

DATA_STREAM_PATTERN = "logs-loghub-*"
ILM_POLICY = "loghub-logs"


def log(msg):
    print(f"[setup] {msg}", flush=True)


def request(method, url, auth, body=None, headers=None, ok=(200, 201, 204)):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    user, password = auth
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            try:
                return resp.status, (json.loads(raw) if raw else None)
            except ValueError:  # plain-text endpoints such as Graylog's lbstatus
                return resp.status, raw.decode(errors='replace')
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw.decode(errors="replace")
        if exc.code in ok:
            return exc.code, payload
        raise RuntimeError(f"{method} {url} -> {exc.code}: {payload}") from None


def wait_for(name, fn, timeout=600):
    deadline = time.time() + timeout
    while True:
        try:
            if fn():
                log(f"{name} is ready")
                return
        except Exception as exc:  # noqa: BLE001 - retry on any transient failure
            last = exc
        else:
            last = "not ready"
        if time.time() > deadline:
            raise SystemExit(f"{name} not ready after {timeout}s: {last}")
        time.sleep(5)


# --------------------------------------------------------------------------- elastic
def setup_elastic():
    auth = ("elastic", os.environ["ELASTIC_PASSWORD"])
    wait_for("elasticsearch", lambda: request("GET", f"{ES}/_cluster/health", auth)[0] == 200)

    request("POST", f"{ES}/_security/user/kibana_system/_password", auth,
            {"password": os.environ["KIBANA_SYSTEM_PASSWORD"]})
    log("kibana_system password set")

    roles = {
        # Logstash only appends documents to the log data streams.
        "loghub_writer": {
            "cluster": ["monitor"],
            "indices": [{"names": [DATA_STREAM_PATTERN],
                         "privileges": ["create_doc", "auto_configure", "view_index_metadata"]}],
        },
        # Grafana: read-only on log data.
        "loghub_reader": {
            "cluster": ["monitor"],
            "indices": [{"names": [DATA_STREAM_PATTERN], "privileges": ["read", "view_index_metadata"]}],
        },
        # Django API: search logs, read cluster stats, manage the retention ILM policy.
        "loghub_api": {
            "cluster": ["monitor", "manage_ilm"],
            "indices": [{"names": [DATA_STREAM_PATTERN],
                         "privileges": ["read", "view_index_metadata", "monitor"]}],
            "applications": [{"application": "kibana-.kibana", "privileges": ["feature_discover.read"],
                              "resources": ["*"]}],
        },
    }
    for name, body in roles.items():
        request("PUT", f"{ES}/_security/role/{name}", auth, body)
    log(f"roles ensured: {', '.join(roles)}")

    users = {
        "logstash_writer": ("LOGSTASH_WRITER_PASSWORD", ["loghub_writer"]),
        "grafana_reader": ("GRAFANA_READER_PASSWORD", ["loghub_reader"]),
        "loghub_api": ("LOGHUB_ES_PASSWORD", ["loghub_api"]),
    }
    for name, (env, user_roles) in users.items():
        request("PUT", f"{ES}/_security/user/{name}", auth,
                {"password": os.environ[env], "roles": user_roles, "full_name": f"LogHub {name}"})
    log(f"users ensured: {', '.join(users)}")

    # Retention: Django updates delete.min_age later via the RetentionPolicy API.
    status, existing = request("GET", f"{ES}/_ilm/policy/{ILM_POLICY}", auth, ok=(200, 404))
    if status == 404:
        request("PUT", f"{ES}/_ilm/policy/{ILM_POLICY}", auth, {"policy": {"phases": {
            "hot": {"actions": {"rollover": {"max_age": "1d", "max_primary_shard_size": "10gb"}}},
            "delete": {"min_age": "14d", "actions": {"delete": {}}},
        }, "_meta": {"managed_by": "loghub"}}})
        log("ILM policy created")

    with open(os.path.join(os.path.dirname(__file__), "index-template.json")) as fh:
        template = json.load(fh)
    request("PUT", f"{ES}/_index_template/logs-loghub", auth, template)
    log("index template ensured")


# --------------------------------------------------------------------------- kibana
def setup_kibana():
    auth = ("elastic", os.environ["ELASTIC_PASSWORD"])
    wait_for("kibana", lambda: request("GET", f"{KIBANA}/api/status", auth)[1]["status"]["overall"]["level"]
             == "available")
    request("POST", f"{KIBANA}/api/data_views/data_view", auth, {
        "data_view": {"id": "loghub-logs", "title": DATA_STREAM_PATTERN, "name": "LogHub logs",
                      "timeFieldName": "@timestamp"},
        "override": True,
    }, headers={"kbn-xsrf": "loghub-setup"})
    request("POST", f"{KIBANA}/api/kibana/settings", auth,
            {"changes": {"defaultIndex": "loghub-logs", "theme:darkMode": True}}, headers={"kbn-xsrf": "loghub-setup"})
    log("kibana data view 'LogHub logs' ensured")


# --------------------------------------------------------------------------- grafana
def setup_grafana():
    admin = (os.environ.get("GRAFANA_ADMIN_USER", "admin"), os.environ["GRAFANA_ADMIN_PASSWORD"])
    wait_for("grafana", lambda: request("GET", f"{GRAFANA}/api/health", admin)[0] == 200)
    status, _ = request("GET", f"{GRAFANA}/api/users/lookup?loginOrEmail=loghub_viewer", admin, ok=(200, 404))
    if status == 404:
        request("POST", f"{GRAFANA}/api/admin/users", admin, {
            "name": "LogHub API", "login": "loghub_viewer", "email": "loghub_viewer@localhost",
            "password": os.environ["GRAFANA_VIEWER_PASSWORD"], "OrgId": 1,
        })
        log("grafana viewer user created")
    else:
        _, user = request("GET", f"{GRAFANA}/api/users/lookup?loginOrEmail=loghub_viewer", admin)
        request("PUT", f"{GRAFANA}/api/admin/users/{user['id']}/password", admin,
                {"password": os.environ["GRAFANA_VIEWER_PASSWORD"]})
        log("grafana viewer user exists; password synced")


# --------------------------------------------------------------------------- graylog
GRAYLOG_INPUTS = [
    {"title": "LogHub GELF UDP", "type": "org.graylog2.inputs.gelf.udp.GELFUDPInput",
     "configuration": {"bind_address": "0.0.0.0", "port": 12201, "recv_buffer_size": 262144,
                       "decompress_size_limit": 8388608}},
    {"title": "LogHub GELF TCP", "type": "org.graylog2.inputs.gelf.tcp.GELFTCPInput",
     "configuration": {"bind_address": "0.0.0.0", "port": 12201, "recv_buffer_size": 1048576,
                       "max_message_size": 2097152, "decompress_size_limit": 8388608,
                       "use_null_delimiter": True, "tls_enable": False}},
]


def setup_graylog():
    admin = ("admin", os.environ["GRAYLOG_ROOT_PASSWORD"])
    headers = {"X-Requested-By": "loghub-setup"}
    wait_for("graylog", lambda: request("GET", f"{GRAYLOG}/api/system/lbstatus", admin,
                                       headers={"Accept": "text/plain"})[0] == 200)

    _, current = request("GET", f"{GRAYLOG}/api/system/inputs", admin)
    titles = {i["title"] for i in current["inputs"]}
    for spec in GRAYLOG_INPUTS:
        if spec["title"] in titles:
            continue
        request("POST", f"{GRAYLOG}/api/system/inputs", admin,
                {**spec, "global": True}, headers=headers)
        log(f"graylog input created: {spec['title']}")

    reader = {
        "username": "loghub_reader", "first_name": "LogHub", "last_name": "API",
        "email": "loghub_reader@localhost", "password": os.environ["GRAYLOG_READER_PASSWORD"],
        "roles": ["Reader"],
        # Read access to the default "All messages" stream plus input/stream metadata.
        "permissions": ["streams:read:000000000000000000000001", "streams:read",
                        "searches:relative", "searches:absolute", "searches:keyword",
                        "inputs:read", "indexsets:read", "system:read", "cluster:read"],
    }
    status, _ = request("GET", f"{GRAYLOG}/api/users/loghub_reader", admin, ok=(200, 404))
    if status == 404:
        request("POST", f"{GRAYLOG}/api/users", admin, reader, headers=headers)
        log("graylog reader user created")
    else:
        _, user = request("GET", f"{GRAYLOG}/api/users/loghub_reader", admin)
        update = {k: v for k, v in reader.items() if k not in ("username", "password")}
        request("PUT", f"{GRAYLOG}/api/users/{user['id']}", admin, update, headers=headers)
        request("PUT", f"{GRAYLOG}/api/users/{user['id']}/password", admin,
                {"password": reader["password"]}, headers=headers)
        log("graylog reader user exists; permissions and password synced")


TARGETS = {"elastic": setup_elastic, "kibana": setup_kibana, "grafana": setup_grafana, "graylog": setup_graylog}

if __name__ == "__main__":
    for target in sys.argv[1:] or ["elastic"]:
        TARGETS[target]()
    log("done")
