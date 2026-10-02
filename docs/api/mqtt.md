# MQTT channel (cloud realtime)

Module `pyairseekers/mqtt.py` (experimental, D9). Reconstructed from the app
v1.7.8 decompile (`libapp.so`); evidence level **observed** unless a field is
exercised against a real Tron. The decompile recovered the `MsgType` enum value
names (they survive `_omitFieldNames` because they are `ProtobufEnum` objects),
so the topic↔message map below is solid; protobuf *field* names inside each
message are still stripped (see `protocol_analysis.md`).

## Transport / connection

MQTT **v5** over TLS (`mqtts://`), mutual-TLS. Everything comes from the
`/api/web/device/iot-cert` bundle (`get_iot_cert()` → `IoTCert`): `ca`,
`cert_key`, `private_key`, `mqtt_broker`, `mqtt_client_id`.

| Param | Value |
|---|---|
| Broker | `mqtt_broker` (host:port parsed from the cert bundle; not a literal) |
| TLS | mutual; `SecurityContext` from `ca` + `cert_key` + `private_key`; ALPN `["mqtt"]` |
| clientIdentifier | `mqtt_client_id` |
| keepAlive | 5 s |
| Clean session | yes (`startClean`) |
| Subscribe QoS | 1 (atLeastOnce) — confirmed |
| Publish QoS / retain | 0 / false — inferred (library defaults; no explicit constant) |

## Topics

`{cid}` = `mqtt_client_id`, `{sn}` = device serial.

| Direction | Topic |
|---|---|
| Uplink (app→cloud commands) | `common/app/{cid}/{sn}/be/up` |
| Subscribe (downlink) | `common/app/{cid}/+/be/down` (`+` = any `sn`) |
| Downlink actual | `common/app/{cid}/{sn}/be/down` |

## Payload

Binary — **not JSON**. Every message is a serialized `Msg` protobuf wrapper
(`src/mower_proto/generate/msg.pb.dart`): tag 2 is the `MsgType` discriminator,
a `bytes` field carries the inner serialized command/response proto, and an
int64 (tag 4) is probably a sequence number. To send: build the inner proto,
`writeToBuffer()`, set it as the `Msg` bytes field, `Msg.writeToBuffer()`,
publish. Inbound is symmetric (`Msg.fromBuffer` → inner `*.fromBuffer`).

## MsgType ↔ message ↔ direction

`*_Req` are uplink, `*_Rsp`/`*_Rsq` downlink, with device-initiated exceptions
(`Upgrade_MCU_Status_Req`, `Task_Report_Req` arrive downlink). The enum has 128
values; the referenced ones:

| MsgType | Name | Inner proto | Dir |
|---|---|---|---|
| 0x00 | Version_Req | VersionReq | up |
| 0x01 | Version_Rsp | VersionRsp | down |
| 0x03 | Battery_Status_Rsp | BatteryStatusRsp | down |
| 0x05 | Sensor_Status_Rsp | SensorStatusRsp | down |
| 0x08 | Upgrade_Status_Rsp | UpgradeStatusRsp | down |
| 0x0a | Create_Map_Rsp | CreateMapRsp | down |
| 0x16 | UnDocking_Rsq | UnDockRsp | down |
| 0x1c | Rtk_Status_Rsq | RtkStatusRsp | down |
| 0x1e | Task_Status_Rsq | TaskStatusRsp | down |
| 0x20 | Clean_Warn_Rsp | — | down |
| 0x33 | Robot_Notice_Rsp | NoticeRsp | down |
| 0x35 | Get_Track_Point_Req | GetTrackReq | up |
| 0x36 | Get_Track_Point_Rsp | GetTrackRsp | down |
| 0x37 | Task_Report_Req | TaskReportReq | down |
| 0x70 | Net_Info_Rsp | NetInfoRsp | down |
| 0x72 | Device_Online_Status_Rsp | DeviceOnlineStatusRsp | down |
| 0x75 | Voice_Upgrade_Status_Rsp | UpgradeStatusRsp | down |
| 0x78 | Set_Config_Rsp | SetConfigRsp | down |
| 0x7a | Get_Config_Rsp | GetConfigRsp | down |
| 0x7b | RTK_info_Req | — | up |
| 0x7c | RTK_info_Rsp | RTKinfoRsp | down |
| 0x7f | Set_Mow_Task_Params_Req | SetMowTaskParamsReq | up |
| 0x80 | Set_Mow_Task_Params_Rsp | SetMowTaskParamsRsp | down |
| 0x8d | Upgrade_MCU_Status_Req | UpgradeMCUStatusReq | down |
| 0x90 | RTK_Reboot_Rsp | RebootRTKRsp | down |
| 0x92 | Full_Status_Rsp | FullStatusRsp | down (composite; fans out to many) |
| 0x9f | Explore_Mapping_Info_Rsp | ExploreMapInfoRsp | down |
| 0xa1 | Get_Explore_Mapping_Track_Point_Rsp | GetExploreMapTrackRsp | down |
| 0xa2 | Get_Explore_Mapping_Boundary_Point_Req | GetExploreMapBoundaryReq | up |
| 0xa3 | Get_Explore_Mapping_Boundary_Point_Rsp | GetExploreMapBoundaryRsp | down |
| 0xa7 | Explore_Map_Upload_Notify_Rsp | — | down |
| 0xab | Obstacle_Dynamic_Clear_Rsp | ObstacleDynamicClearRsp | down |
| 0xad | Obstacle_Dynamic_Boundary_Rsp | ObstacleDynamicBoundaryRsp | down |

Source: app v1.7.8 decompile (`network/mqtt_client.dart`, `network/mqttRsp/*`,
`src/mower_proto/generate/msg.*`). Promotion to `verified` needs a broker
capture against a real device (Q10).
