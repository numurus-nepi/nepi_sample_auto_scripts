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
# Uses onboard ROS python library to
# 1. Checks if AI input image topic exists
# 2. Try's to set reslution on camera 
# 3. Loads selected AI model
# 4. Starts AI detection process using input image stream
# 5. Stops AI detection process on shutdown

import time
import sys
import rospy   

from sensor_msgs.msg import Image
from std_msgs.msg import UInt8, Empty, String, Bool
from nepi_ros_interfaces.msg import ClassifierSelection, StringArray

#####################################################################################
# SETUP - Edit as Necessary ##################################
##########################################

#Set AI Detector Image ROS Topic Type
IMAGE_INPUT_TOPIC_TYPE = "color_2d_image"

#Set AI Detector Parameters
DETECTION_MODEL = "common_object_detection"
DETECTION_THRESHOLD = 0.5

# NEPI ROS namespace setup
NEPI_BASE_NAMESPACE = "/nepi/s2x/"

# AI Detector Publish Topics
AI_START_TOPIC = NEPI_BASE_NAMESPACE + "start_classifier"
AI_STOP_TOPIC = NEPI_BASE_NAMESPACE + "stop_classifier"

#####################################################################################
# Globals
#####################################################################################
stop_classifier_pub = rospy.Publisher(AI_STOP_TOPIC, Empty, queue_size=10)
#####################################################################################
# Methods
#####################################################################################

### System Initialization processes
def initialize_actions():
  print("")
  print("Starting Initialization")  
  # Wait for message
  print("Waiting for topic type: " + IMAGE_INPUT_TOPIC_TYPE)
  topic_name=wait_for_topic_type(IMAGE_INPUT_TOPIC_TYPE)
  print("Found topic: " + topic_name)
  # Classifier initialization, and wait for it to publish
  start_classifier_pub = rospy.Publisher(AI_START_TOPIC, ClassifierSelection, queue_size=1)
  classifier_selection = ClassifierSelection(img_topic=topic_name, classifier=DETECTION_MODEL, detection_threshold=DETECTION_THRESHOLD)
  time.sleep(1) # Important to sleep between publisher constructor and publish()
  rospy.loginfo("Starting object detector: " + str(start_classifier_pub.name))
  start_classifier_pub.publish(classifier_selection)
  print("Initialization Complete")

### Function to wait for topic type to exist
def find_topic_type(topic_type):
  topic_name = ""
  topic_list=rospy.get_published_topics(namespace='/')
  for topic in topic_list:
    if topic[0].find(topic_type) != -1:
      topic_name = topic[0]
  return topic_name

### Function to wait for topic type to exist
def wait_for_topic_type(topic_type):
  topic_name = ""
  while topic_name == "" and not rospy.is_shutdown():
    topic_name=find_topic_type(topic_type)
    time.sleep(.1)
  return topic_name

### Function to wait for topic to exist
def wait_for_topic(topic_name,message_name):
  topic_in_list = False
  while topic_in_list is False and not rospy.is_shutdown():
    topic_list=rospy.get_published_topics(namespace='/')
    topic_to_connect=[topic_name, message_name]
    if topic_to_connect not in topic_list:
      time.sleep(.1)
    else:
      topic_in_list = True


### Cleanup processes on node shutdown
def cleanup_actions():
  global stop_classifier_pub
  print("Shutting down: Executing script cleanup actions")
  stop_classifier_pub.publish(Empty())

### Script Entrypoint
def startNode():
  rospy.loginfo("Starting AI Detection Start automation script", disable_signals=True) # Disable signals so we can force a shutdown
  rospy.init_node(name="ai_detection_setup_start_auto_script")
  # Run initialization processes
  initialize_actions()
  # run cleanup actions on shutdown
  rospy.on_shutdown(cleanup_actions)
  # Spin forever
  rospy.spin()
  
  


#####################################################################################
# Main
#####################################################################################

if __name__ == '__main__':
  startNode()

