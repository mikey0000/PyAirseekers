# Live video (WHEP)

Module `pyairseekers/live.py`. Evidence: **verified** for URL minting and the
offer/answer exchange (capture, 2026-10-01); playback through Home Assistant
not yet confirmed.

## Flow

1. `POST /api/web/live/open {"sn": "<sn>", "camera": 1|2|3}` → `data.url`.
   Cameras: **1 front, 2 left, 3 right** (`const.CAMERA_FRONT/LEFT/RIGHT`;
   confirmed by a Tron owner, 2026-10-02).

   ```
   http://living-eu.airseekers-robotics.com/rtc/v1/whep/?app=live&stream=<sn>_<camera>&secret=<jwt>
   ```

   `secret` is an HS256 JWT `{"camera", "sn", "exp"}` that expires minutes
   after issue. Fetch one per session; never log it (D13).
2. `POST <url>` with `Content-Type: application/sdp` and a recvonly offer
   (audio + video). The server is SRS 6.0.184 (`Server: SRS/6.0.184(Hang)`);
   it answers 201 with the SDP answer and a `Location` for the session.
3. Media flows between the client's WebRTC peer and SRS. SRS is ICE-lite with
   its candidates in the answer; client candidates need not be trickled.
4. While someone watches, the host calls `POST /api/web/live/heartbeat
   {"sn", "camera"}` (Bearer token; answer `data: null`) every
   `LIVE_HEARTBEAT_INTERVAL_S`; without it the cloud lets the stream lapse.
   The library does not schedule this (architecture §5).
5. `DELETE <Location>` ends the WHEP session (`whep_stop`); stopping the
   heartbeat lets the cloud end the robot side.

`whep_play(session, url, offer) -> LiveStream(answer_sdp, resource_url)`;
both fields are hidden from `repr`. A refused offer raises
`AirseekersApiError(code=<http status>)` without the URL.

Mobile data for streams over 4G is not a concern (free at present, per the
owner). Open: the app's heartbeat interval and how long a stream survives
without one (Q12). The app offers VP8, VP9,
AV1, H264 and H265; which one SRS picks for the Tron is not recorded yet.
