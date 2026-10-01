# Open questions

Things the evidence does not settle. Each has the conservative reading the
code takes today and what would close it. Closed questions are deleted and
their answer lands in `decisions.md` or `docs/api/`.

## Q3. What does a login failure look like?

Only "wrong password" is known to be non-zero. Today: any non-success login is
treated as a rejection and is terminal (D5), so a transient server-side
failure would also need `set_credentials`. Closes with captures of a wrong
password, an unknown email and a locked account.

## Q4. Which app headers does the server require?

The app (1.7.8, captured 2026-10-02) sends `accept-language`, `app-version`
(`1.7.8(2026092001)`), `content-type`, `country-code` (ISO country),
`user-agent: Dart/3.11 (dart:io)`, `x-app-device-model`, `x-app-device-os`,
`x-app-device-uuid` (per install) and `x-app-request-time` (unix seconds).
Today: we send `accept-language`, `app-version` and `content-type` only, and
deliberately do not imitate a device. Closes by calling each endpoint without
the extra headers; if `x-app-request-time` turns out to be checked, add it
(it is not an identity).

## Q5. Which read endpoints answer "empty" with a non-zero code?

Known: 407 on firmware/latest, 701 on extended-warranty. Others (task-record
on a new device, map on an unmapped device) may do the same. Today: raise.
Closes by exercising each read on a freshly bound device.

## Q6. The refresh-token grant

`/api/web/user/refresh-token` with `{"refresh_token"}` comes from app
analysis and has never been seen to succeed. Today: tried once on a stale
token, then password login. Closes with a capture.

## Q7. Token lifetime and proactive renewal

The access token is an HS256 JWT `{email, exp, sub}`. In the 2026-10-02
capture `exp` was about 2 h after the requests (issue time not seen), so the
original 23 h assumption was wrong. Today: renew reactively on an auth
failure (D5). Open: whether to renew ahead of `exp` instead, which would save
one failed request every couple of hours.

## Q8. Lock / unlock body

The two sources disagree: `{"sn", "password"}` versus `{"device_id"}`.
Today: `{"sn", "password"}`, unverified. Same doubt for bind, unbind and
firmware upgrade (`device_id` versus `sn`).

## Q9. Regional hosts

Does the login `host` always carry a scheme, and what do non-EU accounts get?
Today: switch only to an absolute `http(s)` URL.

## Q10. MQTT topics

The certificate endpoint is known; topic names (`device/{id}/status`) were
guessed. Closes with a broker capture.

## Q11. Local command schemas

`mower_msgs/Trigger` request schema and command codes, and safe-stop via
`/controller/ctrl`, must be read from `advertiseServices` and tested on a
mower before any local command (D3).

## Q12. Heartbeat interval

Two app heartbeats were captured 38 s apart (`x-app-request-time`
1790894131 → 1790894169), both with the 36-byte `{sn, camera}` body. Today:
`LIVE_HEARTBEAT_INTERVAL_S = 20`, inside that gap even if the two were not
consecutive. Closes with a longer capture (several beats in a row) and the
time a stream survives without one.
