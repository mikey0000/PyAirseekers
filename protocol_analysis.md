# AirSeekers Protocol Analysis

Based on analysis of `dump.dart` - a memory dump from the AirSeekers robotic mower application.

## Overview

The AirSeekers application uses a dual communication architecture:
- **MQTT** for cloud connectivity and remote control
- **Bluetooth Low Energy (BLE)** for direct local device communication

All messages use Protocol Buffers (protobuf) for serialization.

## Protobuf Message Structure

### Core Message Container

#### Main Message (`Msg`)
```protobuf
// Location: package:airseekers/src/mower_proto/generate/msg.pb.dart
message Msg {
  MsgType msgType = 1;      // Message type enum
  uint32 msgSeq = 2;        // Message sequence number  
  bytes msgContent = 3;     // Serialized message payload
}
```

#### Message Types Enum (`MsgType`)
```protobuf
// Location: package:airseekers/src/mower_proto/generate/msg.pbenum.dart
enum MsgType {
  // Request/Response pairs for various operations
  // Specific values need reverse engineering from runtime
}
```

### Protocol Categories

The protocol is organized into 7 main categories:

#### 1. Common (`common.pb.dart`)
Core data structures:
- `TrackPoint` - GPS tracking points with type classification
- `Point` - Basic X/Y coordinate pairs  
- `Pose` - Position and orientation data

```protobuf
message TrackPoint {
  Point point = 1;              // X/Y coordinates
  TrackPoint_Type type = 2;     // Point type enum
}

message Point {
  // X/Y coordinate fields
}
```

#### 2. Status (`status.pb.dart`) 
Device status messages:
- `DeviceOnlineStatusRsp` - Device connectivity status
- `TaskStatusRsp` - Current task execution status

```protobuf
message TaskStatusRsp {
  TaskType type = 1;           // Task type identifier
  // Additional mowing task status fields
}
```

#### 3. Task Management (`task.pb.dart`)
Task control and monitoring:
- `GetTrackRsp` - GPS track data response
- `StartTaskRsp` - Task initiation response
- `SetMowTaskParamsRsp` - Mowing parameter configuration

#### 4. Mapping (`map.pb.dart`)
Map creation and management:
- `CreateMapRsp` - Map creation response with error codes

#### 5. Network (`network.pb.dart`)
Network configuration:
- `NetBaseInfo` - Network base information
- `NetInfoRsp` - Network info with WiFi/4G IP addresses

#### 6. RTK GPS (`rtk.pb.dart`)
Real-Time Kinematic GPS functionality:
- `RTKinfo` - RTK GPS information and corrections
- `Quality` - Signal quality metrics
- `BaseInfo` - RTK base station information
- `BindRTK` - RTK binding operations

#### 7. Teleoperation (`teleop.pb.dart`)
Manual control functionality:
- Remote control messages
- Manual navigation commands

## MQTT Communication

### Core MQTT Client
**Class**: `ASMqttClient` (package:airseekers/network/mqtt_client.dart)
**Library**: `package:mqtt_client/mqtt_client.dart`

### Key Methods
- `publishMessage()` - Send messages to MQTT broker
- `publishGetOnlineStatus()` - Publish device online status
- `publishGetNetwork()` - Publish network status requests
- `publishAllQua()` - Publish quality/status information
- `onConnected()` - Handle MQTT connection events
- `onDisconnected()` - Handle MQTT disconnection events
- `onAutoReconnect()` - Handle automatic reconnection
- `listenerNetwork()` - Network event listener

### Message Structure
- Messages serialized using protobuf (`writeToBuffer()`, `toBuffer()`)
- Uses `MqttPublishMessage` with QoS settings
- `PublicationTopic` for topic management
- Message identifiers for tracking

## Bluetooth Low Energy Communication

### Core Library
**Primary**: `package:flutter_blue_plus/flutter_blue_plus.dart`
**Utilities**: 
- `package:airseekers/utils/blue_tooth_util.dart`
- `package:airseekers/utils/bluetooth_protocol.dart`

### BLE Communication Classes
- `BmConnectRequest` - BLE connection requests
- `BmWriteCharacteristicRequest` - BLE characteristic writes
- `BmWriteType` - Enum for different write operation types

### Communication Pattern
- Connection management through Flutter Blue Plus
- Characteristic-based communication (standard BLE pattern)
- Custom protocol handling for robotic mower communication
- UUID-based device identification

## Message Serialization

### Protobuf Serialization Methods
- `writeToBuffer()` - Serialize messages to binary format
- `writeToCodedBufferWriter()` - Low-level binary writing
- `toBuffer()` - Convert to Uint8List buffer
- `fromBuffer()` - Deserialize from binary (implied usage)

### Field Management
- Field numbers and types managed by `BuilderInfo`
- `_FieldSet` for field management and validation
- Type validation through `_validateField()`
- Field setters like `msgSeq=`, `msgType=`

### Supported Field Types
- **Integer fields** - `_setUnsignedInt32()`, `_writeInt32()`, `_writeInt64()`
- **String fields** - String handling with UTF-8 encoding
- **Binary fields** - `_setByte()`, byte array handling
- **List fields** - `PbList` for repeated fields
- **Enum fields** - Various `.pbenum.dart` files for enumerated types

## Communication Architecture

### Message Flow
1. Application creates protobuf messages with specific field types and numbers
2. Messages are serialized to binary format using protobuf
3. **For MQTT**: Published to specific topics with QoS levels
4. **For BLE**: Sent through Bluetooth characteristics
5. Responses handled through event listeners and callbacks

### Key Communication Classes
- `HttpClient` - REST API communication
- `ASMqttClient` - MQTT messaging and broker connectivity
- Bluetooth utilities - BLE device communication
- Event bus system - Internal message routing

## Example Usage Patterns

### Message Construction
```dart
// Creating a main message wrapper
var msg = Msg()
  ..msgType = MsgType.SOME_TYPE
  ..msgSeq = sequenceNumber
  ..msgContent = serializedPayload;

// RTK binding example
var bindRTK = BindRTK()
  ..bindResult = result;

// Task status example
var taskStatus = TaskStatusRsp()
  ..type = TaskType.MOWING;
```

### Communication Patterns
1. **Request/Response Pattern** - Most operations follow req/rsp naming convention
2. **Status Updates** - Device publishes status periodically via MQTT
3. **Task Management** - Commands sent via protobuf messages
4. **GPS Tracking** - TrackPoint arrays for navigation path data
5. **Network Configuration** - IP address and connectivity management
6. **Mapping Operations** - Map creation and boundary management

## Device Communication Protocols

### MQTT Topics (Inferred)
- Device status publishing
- Command message routing
- Network status updates
- Quality metrics reporting

### Bluetooth Characteristics (Inferred)
- Device control commands
- Real-time status updates
- Local configuration changes
- Emergency stop functionality

## Technical Notes

### Limitations of Analysis
This analysis is based on a memory dump of the Dart application. For complete protocol reconstruction, additional information would be needed:

1. **Exact Field Numbers** - Protobuf field numbers not fully extracted
2. **Enum Values** - Specific enum integer mappings need runtime analysis
3. **MQTT Topics** - Actual topic structure requires network traffic analysis
4. **BLE UUIDs** - Specific characteristic UUIDs need device inspection

### Reverse Engineering Recommendations
1. Analyze actual network traffic (MQTT and BLE)
2. Extract protobuf descriptors from compiled application
3. Monitor device communication in real-time
4. Access original `.proto` definition files if available

## File Locations Referenced

All protobuf definitions located in:
`package:airseekers/src/mower_proto/generate/`

- `common.pb.dart` & `common.pbenum.dart`
- `map.pb.dart` & `map.pbenum.dart`
- `msg.pb.dart` & `msg.pbenum.dart`
- `network.pb.dart` & `network.pbenum.dart`
- `rtk.pb.dart`
- `status.pb.dart` & `status.pbenum.dart`
- `task.pb.dart` & `task.pbenum.dart`
- `teleop.pb.dart` & `teleop.pbenum.dart`

Communication utilities in:
- `package:airseekers/network/mqtt_client.dart`
- `package:airseekers/utils/blue_tooth_util.dart`
- `package:airseekers/utils/bluetooth_protocol.dart`