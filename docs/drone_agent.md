# DroneAgent Documentation

## Overview
The DroneAgent is an autonomous surveillance agent that operates in two modes: AUTONOMOUS and CONTROLLED. It monitors an area using both its own camera and fixed cameras, analyzes images for suspicious activity, and coordinates with a GuardAgent for security response.

## Operation Modes

### Autonomous Mode
In this mode, the drone:
1. Actively monitors the environment
2. Corrects position drift
3. Takes and analyzes pictures
4. Reports suspicious activities to the guard
5. Maintains surveillance patterns

### Controlled Mode
In this mode, the drone:
1. Accepts direct control from a guard
2. Only processes control-end messages
3. Suspends autonomous planning
4. Follows guard commands

## Core Components

### State Management
The drone maintains several key states:
- Current position
- Operation mode (AUTONOMOUS/CONTROLLED)
- Current drift vector
- Picture collection
- Analysis scores
- Guard reference
- Temperature (for analysis sensitivity)

### Event Processing
Processes multiple event types:
- `drone_position_update`: Position updates from Unity client
- `drone_drift_update`: Environmental drift effects
- `drone_camera_capture`: Drone camera images
- `fixed_camera_capture`: Fixed security camera images

### Message Types
Handles various message types for guard coordination:
- `SUSPICIOUS_ACTIVITY`: Reports detected threats
- `CONTROL_REQUEST`: Guard requesting drone control
- `CONTROL_ACCEPTED`: Confirming control transfer
- `CONTROL_ENDED`: Returning to autonomous mode

## Agent Cycle

### 1. Perception (perceive)
The drone gathers environmental information by:
1. Updating drift information from wind effects
2. Getting current position from Unity client
3. Collecting pictures from all cameras

### 2. Planning (plan)
Planning varies by operation mode:

#### Autonomous Planning
1. Message Processing:
   - Checks for control requests
   - Handles control end messages
   
2. Task Planning:
   - Analyzes collected pictures
   - Plans drift corrections
   - Schedules routine surveillance
   - Processes suspicious activity reports

#### Controlled Planning
- Only processes control-end messages
- No autonomous task planning

### 3. Execution (step)
Executes planned steps in sequence:
1. `TAKE_PICTURE`: Captures drone camera images
2. `ANALYZE_PICTURE`: Processes images for threats
3. `REPORT_SUSPICIOUS_ACTIVITY`: Alerts guard of threats
4. `ACCEPT_CONTROL_REQUEST`: Transfers control to guard
5. `CHECK_FIXED_CAMERAS`: Monitors fixed cameras
6. `MOVE_TO_POSITION`: Corrects position/drift

## Communication Flow

### Unity Client Communication
- Sends movement commands
- Receives position updates
- Receives camera captures
- Processes drift updates

### Guard Communication
- Receives control requests
- Sends control acceptance
- Reports suspicious activities
- Receives control end messages

## Image Processing

### Collection
1. Drone camera images
2. Fixed security camera feeds
3. Base64 encoded format
4. Cached in pictures dictionary

### Analysis
1. Uses GPT-4-Vision for threat detection
2. Caches results by image hash
3. Scores threats from 0 to 1
4. Reports high scores (>0.7) to guard

## Position Management

### Drift Handling
1. Accumulates drift vectors from environment
2. Calculates correction positions
3. Issues movement commands to counter drift
4. Maintains desired surveillance position

### Movement
1. Receives target positions
2. Sends movement commands to Unity
3. Updates internal position state
4. Logs position changes

## Error Handling
- Comprehensive logging throughout operations
- Graceful handling of missing guard references
- Recovery from communication failures
- Cache management for analysis results
