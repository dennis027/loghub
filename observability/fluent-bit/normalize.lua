-- Normalizes records from every input, enforces the collector's organization,
-- masks secrets, and computes a GELF level so either route gets clean events.

local COLLECTOR_ORG = os.getenv("COLLECTOR_DEFAULT_ORG") or "default"
local MAX_MESSAGE = 32768
local ROUTES = { elk = true, graylog = true, both = true }

local SENSITIVE_KEYS = { "password", "passwd", "secret", "token", "api_key", "apikey",
                         "authorization", "cookie", "credential", "private_key", "access_key" }
local SAFE_KEYS = { fingerprint = true, trace_id = true, span_id = true, log_route = true }

local LEVELS = {
  trace = "debug", debug = "debug",
  info = "info", information = "info", notice = "info",
  warn = "warning", warning = "warning",
  err = "error", error = "error",
  crit = "critical", critical = "critical", fatal = "critical",
  alert = "critical", emerg = "critical", emergency = "critical", panic = "critical",
}
local GELF_LEVEL = { debug = 7, info = 6, warning = 4, error = 3, critical = 2 }
local SYSLOG_SEVERITY = { [0] = "critical", "critical", "critical", "error", "warning", "info", "info", "debug" }

-- Build a case-insensitive Lua pattern for a literal word.
local function ci(word)
  return (word:gsub("%a", function(c) return "[" .. c:lower() .. c:upper() .. "]" end))
end

local MESSAGE_PATTERNS = {}
for _, key in ipairs({ "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
                       "access_key", "authorization" }) do
  table.insert(MESSAGE_PATTERNS, "(" .. ci(key) .. "[\"']?%s*[:=]%s*[\"']?)([^%s\"'&,;}]+)")
end

local function mask_string(s)
  s = s:gsub("(" .. ci("bearer") .. "%s+)[%w%-%._~%+/]+=*", "%1[REDACTED]")
  for _, pattern in ipairs(MESSAGE_PATTERNS) do
    s = s:gsub(pattern, "%1[REDACTED]")
  end
  return s
end

local function is_sensitive(key)
  if SAFE_KEYS[key] then return false end
  local lower = string.lower(key)
  for _, needle in ipairs(SENSITIVE_KEYS) do
    if string.find(lower, needle, 1, true) then return true end
  end
  return false
end

local function mask(tbl, depth)
  for k, v in pairs(tbl) do
    local t = type(v)
    if type(k) == "string" and is_sensitive(k) and (t == "string" or t == "number") then
      tbl[k] = "[REDACTED]"
    elseif t == "string" then
      tbl[k] = mask_string(v)
    elseif t == "table" and depth < 5 then
      mask(v, depth + 1)
    end
  end
end

local function starts_with(s, prefix)
  return string.sub(s, 1, #prefix) == prefix
end

function normalize(tag, timestamp, record)
  -- Docker fluentd logging driver
  if record["log"] ~= nil and record["message"] == nil then
    record["message"] = record["log"]
    record["log"] = nil
  end
  if type(record["container_name"]) == "string" then
    record["container"] = (record["container_name"]:gsub("^/", ""))
    record["container_name"] = nil
  end
  local compose_service = record["com.docker.compose.service"]
  if compose_service ~= nil then
    record["service"] = record["service"] or compose_service
    record["com.docker.compose.service"] = nil
  end
  if record["com.docker.compose.project"] ~= nil then
    record["compose_project"] = record["com.docker.compose.project"]
    record["com.docker.compose.project"] = nil
  end
  if record["source"] ~= nil and record["stream"] == nil and starts_with(tag, "docker.") then
    record["stream"] = record["source"]
    record["source"] = nil
  end

  -- Syslog
  if starts_with(tag, "syslog.") then
    record["hostname"] = record["hostname"] or record["host"]
    record["host"] = nil
    record["service"] = record["service"] or record["ident"]
    record["ident"] = nil
    record["time3164"] = nil
    record["time5424"] = nil
    local pri = tonumber(record["pri"])
    if pri ~= nil and record["level"] == nil then
      record["level"] = SYSLOG_SEVERITY[pri % 8]
    end
    record["source_type"] = record["source_type"] or "syslog"
  elseif starts_with(tag, "docker.") then
    record["source_type"] = record["source_type"] or "docker"
  end

  -- Tenant enforcement: unauthenticated collector inputs cannot choose an organization.
  if not starts_with(tag, "ingest.") and not starts_with(tag, "graylog.ingest.") then
    record["organization"] = COLLECTOR_ORG
    record["collector"] = record["collector"] or "fluent-bit"
  end

  if not ROUTES[record["log_route"] or ""] then
    record["log_route"] = "elk"
  end

  local level = record["level"] or record["levelname"] or record["severity"]
  if type(level) == "string" then
    record["level"] = LEVELS[string.lower(level)] or record["level"]
  end
  record["levelname"] = nil
  record["gelf_level"] = GELF_LEVEL[record["level"] or "info"] or 6

  if type(record["message"]) == "string" and #record["message"] > MAX_MESSAGE then
    record["message"] = string.sub(record["message"], 1, MAX_MESSAGE) .. " …[truncated]"
  end
  if record["message"] == nil then
    record["message"] = ""
  end

  mask(record, 0)
  return 2, timestamp, record
end
