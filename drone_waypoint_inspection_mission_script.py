#!/usr/bin/env python
#
# NEPI Dual-Use License
# Project: nepi_sample_auto_scripts
#
# This license applies to any user of NEPI Engine software
#
# Copyright (C) 2023 Numurus, LLC <https://www.numurus.com>
# see https://github.com/numurus-nepi/nepi_edge_sdk_base
#
# This software is dual-licensed under the terms of either a NEPI software developer license
# or a NEPI software commercial license.
#
# The terms of both the NEPI software developer and commercial licenses
# can be found at: www.numurus.com/licensing-nepi-engine
#
# Redistributions in source code must retain this top-level comment block.
# Plagiarizing this software to sidestep the license obligations is illegal.
#
# Contact Information:
# ====================
# - https://www.numurus.com/licensing-nepi-engine
# - mailto:nepi@numurus.com
#
#


# Sample NEPI Automation Script.
# Uses onboard ROS python and mavros libraries to
# 1) Subscribes to NEPI nav_pose_current heading, orientation, position, location topics
# 2) Runs pre-mission processes
# 3) Runs mission goto command processes
# 4) Runs mission goto action processes
# 5) Runs post-mission processes

# Requires the following additional scripts are running
# a) ardupilot_rbx_driver_script.py
# (Optional) Some Snapshot Action Automation Script like the following
#   b)snapshot_event_save_to_disk_action_script.py
#   c)snapshot_event_send_to_cloud_action_script.py
# d) (Optional) ardupilot_rbx_fake_gps_process_script.py if a real GPS fix is not available
# These scripts are available for download at:
# [link text](https://github.com/numurus-nepi/nepi_sample_auto_scripts)

import rospy
import time
import numpy as np
import math
import tf

from std_msgs.msg import Empty, Int8, UInt8, Bool, String, Float32, Float64, Float64MultiArray
from nav_msgs.msg import Odometry
from sensor_msgs.msg import NavSatFix
from geometry_msgs.msg import Point, Pose, Quaternion, Twist, Vector3, PoseStamped
from geographic_msgs.msg import GeoPoint, GeoPose, GeoPoseStamped
from mavros_msgs.msg import State, AttitudeTarget
from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest, CommandTOL, CommandHome

#####################################################################################
# SETUP - Edit as Necessary ##################################
##########################################


# goto Position Global Settings
###################################################
# goto_location is [LAT, LONG, ALT_WGS84, YAW_NED_DEGREES]
# Altitude is specified as meters above the WGS-84 and converted to AMSL before sending
# Yaw is specified in NED frame degrees 0-360 or +-180 
#####################################################
GOTO_LOCATION = [47.6541208,-122.3186620, 10, -999] # [Lat, Long, Alt WGS84, Yaw NED Frame], Enter -999 to use current value
GOTO_LOCATION_CORNERS =  [[47.65412620,-122.31881480, -999, -999],[47.65402050,-122.31875320, -999, -999],[47.65391570,-122.31883630, -999, -999],[47.65397990,-122.31912330, -999, -999]]

# goto Position Local Body Settings
###################################################
# goto_position is [X_BODY_METERS, Y_BODY_METERS, Z_BODY_METERS, YEW_BODY_DEGREES]
# Local Body Position goto Function use these body relative x,y,z,yaw conventions
# x+ axis is forward
# y+ axis is right
# z+ axis is down
# Only yaw orientation updated
# yaw+ clockwise, yaw- counter clockwise from x axis (0 degrees faces x+ and rotates positive using right hand rule around z+ axis down)
#####################################################
GOTO_POSITION = [10,5,0,0] # [X, Y, Z, YAW] Offset in xyz meters yaw body +- 180 (+Z is Down). Use 0 value for no change

# goto Attitude NED Settings
###################################################
# goto_attitudeInp is [ROLL_NED_DEG, PITCH_NED_DEG, YEW_NED_DEGREES]
###################################################
GOTO_POSE = [-999,30,-999] # Roll, Pitch, Yaw Degrees: Enter -999 to use current value


###################################################
# RBX State and Mode Dictionaries
RBX_STATES = ["DISARM","ARM"]
RBX_MODES = ["STABILIZE","LAND","RTL","LOITER","GUIDED","RESUME"]
RBX_ACTIONS = ["TAKEOFF"] 

# goto ACTION SETTINGS
SNAPSHOT_EVENT_WAIT_SEC = 5.0 # Time to wait for snapshot event to complete

# ROS namespace setup
NEPI_BASE_NAMESPACE = "/nepi/s2x/"
NEPI_NAVPOSE_SERVICE_NAME = NEPI_BASE_NAMESPACE + "nav_pose_query"
NEPI_RBX_NAMESPACE = NEPI_BASE_NAMESPACE + "ardupilot/rbx/"


# NEPI MAVLINK RBX Driver Capabilities Publish Topics
NEPI_RBX_CAPABILITIES_NAVPOSE_TOPIC = NEPI_RBX_NAMESPACE + "navpose_support"
NEPI_RBX_CAPABILITIES_STATES_TOPIC = NEPI_RBX_NAMESPACE + "state_options"
NEPI_RBX_CAPABILITIES_MODES_TOPIC = NEPI_RBX_NAMESPACE + "mode_options"
NEPI_RBX_CAPABILITIES_ACTIONS_TOPIC = NEPI_RBX_NAMESPACE + "actions_options"

# NEPI MAVLINK RBX Driver Status Publish Topics
NEPI_RBX_STATUS_STATE_TOPIC = NEPI_RBX_NAMESPACE + "state"  # Int to Defined Dictionary RBX_STATES
NEPI_RBX_STATUS_MODE_TOPIC = NEPI_RBX_NAMESPACE + "mode" # Int to Defined Dictionary RBX_MODES
NEPI_RBX_STATUS_READY_TOPIC = NEPI_RBX_NAMESPACE + "ready" # Bool, True if goto is complete or no active goto process
NEPI_RBX_STATUS_GOTO_ERRORS_TOPIC = NEPI_RBX_NAMESPACE + "goto_errors" # Floats [X_Meters,Y_Meters,Z_Meters,Heading_Degrees,Roll_Degrees,Pitch_Degrees,Yaw_Degrees]
NEPI_RBX_STATUS_CMD_SUCCESS_TOPIC = NEPI_RBX_NAMESPACE + "cmd_success" # Bool - Any command that changes ready state
# NEPI MAVLINK RBX Driver Settings Subscriber Topics
NEPI_RBX_SET_STATE_TOPIC = NEPI_RBX_NAMESPACE + "set_state" # Int to Defined Dictionary RBX_STATES
NEPI_RBX_SET_MODE_TOPIC = NEPI_RBX_NAMESPACE + "set_mode"  # Int to Defined Dictionary RBX_MODES
NEPI_RBX_SET_HOME_CURRENT_TOPIC = NEPI_RBX_NAMESPACE + "set_home_current" # Emplty

# NEPI MAVLINK RBX Driver Control Subscriber Topics
NEPI_RBX_SET_ACTION_TOPIC = NEPI_RBX_NAMESPACE + "set_action"  # Int to Defined Dictionary RBX_MODES
NEPI_RBX_GOTO_POSE_TOPIC = NEPI_RBX_NAMESPACE + "goto_pose" # Ignored if any active goto processes
NEPI_RBX_GOTO_POSITION_TOPIC = NEPI_RBX_NAMESPACE + "goto_position" # Ignored if any active goto processes
NEPI_RBX_GOTO_LOCATION_TOPIC = NEPI_RBX_NAMESPACE + "goto_location" # Ignored if any active goto processes

# goto Action Topics
SNAPSHOT_TOPIC = NEPI_BASE_NAMESPACE + "snapshot_event"

#####################################################################################
# Globals
#####################################################################################
rbx_set_state_pub = rospy.Publisher(NEPI_RBX_SET_STATE_TOPIC, UInt8, queue_size=1)
rbx_set_mode_pub = rospy.Publisher(NEPI_RBX_SET_MODE_TOPIC, UInt8, queue_size=1)
rbx_set_action_pub = rospy.Publisher(NEPI_RBX_SET_ACTION_TOPIC, UInt8, queue_size=1)


rbx_goto_pose_pub = rospy.Publisher(NEPI_RBX_GOTO_POSE_TOPIC, Float64MultiArray, queue_size=1)
rbx_goto_position_pub = rospy.Publisher(NEPI_RBX_GOTO_POSITION_TOPIC, Float64MultiArray, queue_size=1)
rbx_goto_location_pub = rospy.Publisher(NEPI_RBX_GOTO_LOCATION_TOPIC, Float64MultiArray, queue_size=1)

snapshot_trigger_pub = rospy.Publisher(SNAPSHOT_TOPIC, Empty, queue_size = 1)

rbx_cap_navpose = None
rbx_cap_states = None
rbx_cap_modes = None
rbx_cap_actions = None

rbx_status_state = None
rbx_status_mode = None
rbx_status_ready = None
rbx_status_goto_errors = None
rbx_status_cmd_success = None

               
#####################################################################################
# Methods
#####################################################################################

### System Initialization processes
def initialize_actions():
  global rbx_cap_navpose
  global rbx_cap_states
  global rbx_cap_modes
  global rbx_cap_actions
  global rbx_status_state
  global rbx_status_mode
  global rbx_status_ready
  global rbx_status_cmd_success
  ### Capabilities Subscribers
  # Wait for topic
  print("Waiting for topic: " + NEPI_RBX_CAPABILITIES_NAVPOSE_TOPIC)
  wait_for_topic(NEPI_RBX_CAPABILITIES_NAVPOSE_TOPIC)
  print("Starting capabilities navpose scubscriber callback")
  rospy.Subscriber(NEPI_RBX_CAPABILITIES_NAVPOSE_TOPIC, UInt8, rbx_cap_navpose_callback)
  while rbx_cap_navpose is None and not rospy.is_shutdown():
    print("Waiting for capabilities navpose to publish")
    time.sleep(0.1)
  print(rbx_cap_navpose)
  # Wait for topic
  print("Waiting for topic: " + NEPI_RBX_CAPABILITIES_STATES_TOPIC)
  wait_for_topic(NEPI_RBX_CAPABILITIES_STATES_TOPIC)
  print("Starting state scubscriber callback")
  rospy.Subscriber(NEPI_RBX_CAPABILITIES_STATES_TOPIC, String, rbx_cap_states_callback)
  while rbx_cap_states is None and not rospy.is_shutdown():
    print("Waiting for capabilities states to publish")
    time.sleep(0.1)
  print(rbx_cap_states)
  # Wait for topic
  print("Waiting for topic: " + NEPI_RBX_CAPABILITIES_MODES_TOPIC)
  wait_for_topic(NEPI_RBX_CAPABILITIES_MODES_TOPIC)
  print("Starting modes scubscriber callback")
  rospy.Subscriber(NEPI_RBX_CAPABILITIES_MODES_TOPIC, String, rbx_cap_modes_callback)
  while rbx_cap_modes is None and not rospy.is_shutdown():
    print("Waiting for capabilities modes to publish")
    time.sleep(0.1)
  print(rbx_cap_modes)
  # Wait for topic
  print("Waiting for topic: " + NEPI_RBX_CAPABILITIES_ACTIONS_TOPIC)
  wait_for_topic(NEPI_RBX_CAPABILITIES_ACTIONS_TOPIC)
  print("Starting actions scubscriber callback")
  rospy.Subscriber(NEPI_RBX_CAPABILITIES_ACTIONS_TOPIC, String, rbx_cap_actions_callback)
  while rbx_cap_actions is None and not rospy.is_shutdown():
    print("Waiting for capabilities actions to publish")
    time.sleep(0.1)
  print(rbx_cap_actions)
  ### Status Subscribers
  # Wait for topic
  print("Waiting for topic: " + NEPI_RBX_STATUS_STATE_TOPIC)
  wait_for_topic(NEPI_RBX_STATUS_STATE_TOPIC)
  print("Starting state scubscriber callback")
  rospy.Subscriber(NEPI_RBX_STATUS_STATE_TOPIC, Int8, rbx_state_callback)
  while rbx_status_state is None and not rospy.is_shutdown():
    print("Waiting for current state to publish")
    time.sleep(0.1)
  print(rbx_status_state)
  # Wait for topic
  print("Waiting for topic: " + NEPI_RBX_STATUS_MODE_TOPIC)
  wait_for_topic(NEPI_RBX_STATUS_MODE_TOPIC)
  print("Starting mode scubscriber callback")
  rospy.Subscriber(NEPI_RBX_STATUS_MODE_TOPIC, Int8, rbx_mode_callback)
  while rbx_status_state is None and not rospy.is_shutdown():
    print("Waiting for current state to publish")
    time.sleep(0.1)
  print(rbx_status_mode)
  # Wait for goto controls status to publish
  print("Waiting for topic: " + NEPI_RBX_STATUS_READY_TOPIC)
  wait_for_topic(NEPI_RBX_STATUS_READY_TOPIC)
  # Start ready status monitor
  print("Starting mavros ready status subscriber")
  rospy.Subscriber(NEPI_RBX_STATUS_READY_TOPIC, Bool, rbx_status_ready_callback)
  while rbx_status_ready is None and not rospy.is_shutdown():
    print("Waiting for ready status to publish")
    time.sleep(0.1)
  # Start goto errors status monitor
  print("Starting mavros goto errors subscriber")
  rospy.Subscriber(NEPI_RBX_STATUS_GOTO_ERRORS_TOPIC, Float64MultiArray, rbx_status_goto_errors_callback)
  while rbx_status_goto_errors is None and not rospy.is_shutdown():
    print("Waiting for goto errors status to publish")
    time.sleep(0.1)
  # Start cmd success status monitor
  print("Starting mavros cmd success subscriber")
  rospy.Subscriber(NEPI_RBX_STATUS_CMD_SUCCESS_TOPIC, Bool, rbx_status_cmd_success_callback)
  while rbx_status_cmd_success is None and not rospy.is_shutdown():
    print("Waiting for cmd success status to publish")
    time.sleep(0.1)
  print("Initialization Complete")

## Function for custom pre-mission actions
def pre_mission_actions():
  ###########################
  # Start Your Custom Actions
  ###########################
  success = True
  # Set Mode to Guided
  set_rbx_mode("GUIDED")
  # Arm System
  set_rbx_state("ARM")
  # Send Takeoff Command
  success=set_rbx_action("TAKEOFF")
  if success:
    print("Takeoff Successful")
  else:
    print("Takeoff Failed")
  ###########################
  # Stop Your Custom Actions
  ###########################
  print("Pre-Mission Actions Complete")
  return success

## Function for custom mission actions
def mission_actions():
  ###########################
  # Start Your Custom Actions
  ###########################
  ## Change Vehicle Mode to Guided
  success = True
  #print("Sending snapshot event trigger")
  #snapshot(5)
  ###########################
  # Stop Your Custom Actions
  ###########################
  print("Mission Actions Complete")
  return success
  
## Function for custom post-mission actions
def post_mission_actions():
  ###########################
  # Start Your Custom Actions
  ###########################
  success = True
  #land() # Uncomment to change to Land mode
  #loiter() # Uncomment to change to Loiter mode
  set_rbx_mode("RTL") # Uncomment to change to Home mode
  #continue_mission() # Uncomment to return to pre goto state
  time.sleep(1)
  ###########################
  # Stop Your Custom Actions
  ###########################
  print("Post-Mission Actions Complete")
  return success

#######################
# RBX Capabilities Callbacks

def rbx_cap_navpose_callback(cap_navpose_msg):
  global rbx_cap_navpose
  rbx_cap_navpose = cap_navpose_msg.data

def rbx_cap_states_callback(cap_states_msg):
  global rbx_cap_states
  cap_states_str = cap_states_msg.data
  rbx_cap_states = eval(cap_states_str)

def rbx_cap_modes_callback(cap_modes_msg):
  global rbx_cap_modes
  cap_modes_str = cap_modes_msg.data
  rbx_cap_modes = eval(cap_modes_str)

def rbx_cap_actions_callback(cap_actions_msg):
  global rbx_cap_actions
  cap_actions_str = cap_actions_msg.data
  rbx_cap_actions = eval(cap_actions_str) 

#######################
# RBX Status Callbacks
### Callback to update rbx current state value
def rbx_state_callback(state_msg):
  global rbx_status_state
  rbx_status_state = state_msg.data  

### Callback to update rbx current mode value
def rbx_mode_callback(mode_msg):
  global rbx_status_mode
  rbx_status_state = mode_msg.data

### Callback to update rbx ready status value
def rbx_status_ready_callback(ready_msg):
  global rbx_status_ready
  rbx_status_ready = ready_msg.data

### Callback to update rbx goto errors status value
def rbx_status_goto_errors_callback(goto_errors_msg):
  global rbx_status_goto_errors
  rbx_status_goto_errors = goto_errors_msg.data  

### Callback to update rbx cmd success status value
def rbx_status_cmd_success_callback(cmd_success_msg):
  global rbx_status_cmd_success
  rbx_status_cmd_success = cmd_success_msg.data

#######################
# RBX Settings Functions

### Function to set rbx state
def set_rbx_state(state_str):
  global rbx_set_state_pub
  print("Setting state")
  print(state_str)
  state_ind = -1
  for ind, state in enumerate(rbx_cap_states):
    if state == state_str:
      state_ind = ind
  if state_ind == -1:
    print("No matching state found")
  else:
    print(state_ind)
    rbx_set_state_pub.publish(state_ind)
    wait_for_rbx_status_busy()
    wait_for_rbx_status_ready()
    time.sleep(1)

### Function to set rbx state
def set_rbx_mode(mode_str):
  print("Setting mode")
  global rbx_set_mode_pub
  mode_ind = -1
  for ind, mode in enumerate(rbx_cap_modes):
    if mode == mode_str:
      mode_ind = ind
  if mode_ind == -1:
    print("No matching mode found")
  else:
    print(mode_ind)
    rbx_set_mode_pub.publish(mode_ind)
    wait_for_rbx_status_busy()
    wait_for_rbx_status_ready()
  time.sleep(1)
    


#######################
# RBX Control Functions

### Function to set rbx action
def set_rbx_action(action_str):
  global rbx_status_cmd_success
  global rbx_set_action_pub
  action_ind = -1
  for ind, action in enumerate(rbx_cap_actions):
    if action == action_str:
      action_ind = ind
  if action_ind == -1:
    print("No matching action found")
    return False
  else:
    rbx_set_action_pub.publish(action_ind)
    wait_for_rbx_status_busy()
    wait_for_rbx_status_ready()
    return rbx_status_cmd_success

### Function to call goto Location Global control
def goto_rbx_location(goto_data):
  global rbx_status_cmd_success
  global rbx_goto_location_pub
  # Send goto Location Command
  wait_for_rbx_status_ready()
  print("Starting goto Location Global Process")
  goto_location_msg = create_goto_message(goto_data)
  rbx_goto_location_pub.publish(goto_location_msg)
  wait_for_rbx_status_busy()
  wait_for_rbx_status_ready()
  return rbx_status_cmd_success

### Function to call goto Position Body control
def goto_rbx_position(goto_data):
  global rbx_goto_location_pub
  # Send goto Position Command
  wait_for_rbx_status_ready()
  print("Starting goto Position Body Process")
  goto_position_msg = create_goto_message(goto_data)
  rbx_goto_position_pub.publish(goto_position_msg)
  wait_for_rbx_status_busy()
  wait_for_rbx_status_ready()

### Function to call goto Attititude NED control
def goto_rbx_pose(goto_data):
  global rbx_goto_pose_pub
  # Send goto Attitude Command
  wait_for_rbx_status_ready()
  print("Starting goto Attitude NED Process")
  goto_attitude_msg = create_goto_message(goto_data)
  rbx_goto_pose_pub.publish(goto_attitude_msg)
  wait_for_rbx_status_busy()
  wait_for_rbx_status_ready()
  
### Function to wait for goto control process to complete
def wait_for_rbx_status_ready():
  global rbx_status_ready
  global rbx_status_goto_errors
  while rbx_status_ready is not True and not rospy.is_shutdown():
    print("Waiting for current cmd process to complete")
    print(rbx_status_ready)
    print("Current Errors")
    print(rbx_status_goto_errors)
    time.sleep(1)

### Function to wait for goto control process to complete
def wait_for_rbx_status_busy():
  global rbx_status_ready
  while rbx_status_ready is not False and not rospy.is_shutdown():
    print("Waiting for cmd process to start")
    print(rbx_status_ready)
    time.sleep(1)

#######################
# Process Functions

### Function for creating goto messages
def create_goto_message(goto):
  print(goto)
  goto_msg = Float64MultiArray()
  goto_data=[]
  for ind in range(len(goto)):
    goto_data.append(float(goto[ind]))
  print(goto_data)
  goto_msg.data = goto_data
  print("")
  print("goto Message Created")
  print(goto_msg)
  return goto_msg

#######################
# Setpoint Action Functions

### Function to send snapshot event trigger and wait for completion
def snapshot(wait_sec):
  global snapshot_trigger_pub
  snapshot_trigger_pub.publish(Empty())
  time.sleep(wait_sec)


#######################
# Initialization Functions

### Function to find a topic
def find_topic(topic_name):
  topic = ""
  topic_list=rospy.get_published_topics(namespace='/')
  for topic_entry in topic_list:
    if topic_entry[0].find(topic_name) != -1:
      topic = topic_entry[0]
  return topic

### Function to check for a topic 
def check_for_topic(topic_name):
  topic_exists = True
  topic=find_topic(topic_name)
  if topic == "":
    topic_exists = False
  return topic_exists

### Function to wait for a topic
def wait_for_topic(topic_name):
  topic = ""
  while topic == "" and not rospy.is_shutdown():
    topic=find_topic(topic_name)
    time.sleep(.1)
  return topic

#######################
# StartNode and Cleanup Functions

### Cleanup processes on node shutdown
def cleanup_actions():
  print("Shutting down: Executing script cleanup actions")

  
### Script Entrypoint
def startNode():
  rospy.loginfo("Starting Drone Waypoint Inspection Mission Script")
  rospy.init_node("drone_waypoint_inspection_mission_script")
  #initialize system including pan scan process
  initialize_actions()
  #########################################
  # Run Pre-Mission Custom Actions
  print("Starting Pre-goto Actions")
  success = pre_mission_actions()
  #########################################
  # Start Mission
  #########################################
  # Send goto Location Command
  print("Starting goto Location Global Process")
  success = goto_rbx_location(GOTO_LOCATION)
  ##########################################
  # Send goto Position Command
  print("Starting goto Position Local Process")
  success = goto_rbx_position(GOTO_POSITION)
  #########################################
  # Send goto Attitude Command
  print("Sending goto Attitude Control Message")
  success = goto_rbx_pose(GOTO_POSE)
  #########################################
  # Run Mission Actions
  print("Starting Mission Actions")
  success = mission_actions()
 #########################################
  # Send goto Location Loop Command
  for ind in range(4):
    # Send goto Location Command
    print("Starting goto Location Corners Process")
    success = goto_rbx_location(GOTO_LOCATION_CORNERS[ind])
    # Run Mission Actions
    print("Starting Mission Actions")
    success = mission_actions()
  #########################################
  # End Mission
  #########################################
  # Run Post-Mission Actions
  print("Starting Post-Goto Actions")
  success = post_mission_actions()
  #########################################
  # Mission Complete, Shutting Down
  print("Shutting Mission Restarting in 20 Seconds")
  time.sleep(20)
  rospy.signal_shutdown("Mission Complete, Shutting Down")
  #########################################
  # Run cleanup actions on rospy shutdown
  rospy.on_shutdown(cleanup_actions)
  # Spin forever
  rospy.spin()


#####################################################################################
# Main
#####################################################################################

if __name__ == '__main__':
  startNode()

