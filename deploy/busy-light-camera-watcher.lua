-- Busy-light camera watcher for Hammerspoon (https://www.hammerspoon.org)
--
-- Turns the led-ticker busy light ON whenever any camera is in use (Zoom,
-- Google Meet, FaceTime, Photo Booth, ...) and OFF when none are, so the
-- corner dot tracks "I'm in a meeting" with no manual toggling. It talks to
-- the busy light's HTTP source (set `source = "http"` in [busy_light]).
--
-- Install:
--   1. Install Hammerspoon and grant it Camera access
--      (System Settings > Privacy & Security > Camera > Hammerspoon).
--   2. Copy this file to ~/.hammerspoon/init.lua, or from your existing
--      init.lua add:  require("busy-light-camera-watcher")  (after copying
--      it next to init.lua).
--   3. Set PI_HOST / PORT / TOKEN below to match your [busy_light] config.
--   4. Reload Hammerspoon (menu-bar icon > Reload Config).
--
-- Caveat: this fires on CAMERA use. A Meet/Zoom call joined with video OFF
-- never turns the camera on, so it won't trigger. It also fires for any
-- app's camera use, not just meetings -- usually what you want for a busy
-- light. macOS has no reliable "another app is using the microphone" event,
-- so camera is the practical signal.
--
-- Docs: https://docs.ledticker.dev/concepts/busy-light/

local PI_HOST = "longboi" -- Pi hostname or IP running led-ticker
local PORT = 8080 -- must match [busy_light] http_port
local TOKEN = "changeme" -- must match [busy_light] token ("" if none)
local TTL = 0 -- per-request auto-clear seconds; 0 = stay on until camera off

local last = nil

local function setBusy(on)
  if on == last then
    return -- debounce: only send on an actual state change
  end
  last = on
  local url = string.format(
    "http://%s:%d/busy?state=%s",
    PI_HOST,
    PORT,
    on and "on" or "off"
  )
  if TOKEN ~= "" then
    url = url .. "&token=" .. TOKEN
  end
  if on and TTL > 0 then
    url = url .. "&ttl=" .. TTL
  end
  hs.http.asyncGet(url, nil, function() end)
end

local function anyCameraInUse()
  for _, cam in pairs(hs.camera.allCameras()) do
    if cam:isInUse() then
      return true
    end
  end
  return false
end

local function check()
  setBusy(anyCameraInUse())
end

local function watch(cam)
  cam:setPropertyWatcherCallback(function()
    check()
  end)
  cam:startPropertyWatcher()
end

for _, cam in pairs(hs.camera.allCameras()) do
  watch(cam)
end

hs.camera.setWatcherCallback(function(cam, state)
  if state == "Added" then
    watch(cam)
  end
  check()
end)
hs.camera.startWatcher()

check() -- sync the light to the current camera state on load
