#!/usr/bin/env python

__author__ = "Jason Seawall"
__copyright__ = "Copyright 2023, Numurus LLC"
__email__ = "nepi@numurus.com"
__credits__ = ["Jason Seawall", "Josh Maximoff"]

__license__ = "GPL"
__version__ = "2.0.4.0"

# Sample NEPI Automation Script. 
# Uses onboard ROS python library to
# 1. Waits for snapshot_event topic message
# 2. Start saving image data to onboard storage
# 3. Delays a specified amount of time, then stops saving
# 4. Delays next trigger event action for some set delay time



import time
import sys
import rospy
import os
import numpy as np
import cv2
import json

from datetime import datetime
from std_msgs.msg import UInt8, Empty, String, Bool, Float64MultiArray
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from nepi_ros_interfaces.msg import NavPose
from nepi_ros_interfaces.srv import NavPoseQuery, NavPoseQueryRequest


###########################################################################
# SETUP - Edit as Necessary 
###########################################################################
SAVE_NAVPOSE_DATA_ENABLED = True # True-Save NavPose File  with each image


###!!!!!!!! Set Image ROS Topic Name to Save  !!!!!!!!
IMAGE_INPUT_TOPIC = "/nepi/s2x/nexigo_n60_fhd_webcam_audio/idx/color_2d_image"
#IMAGE_INPUT_TOPIC = "/nepi/s2x/see3cam_cu81/idx/color_2d_image"
#IMAGE_INPUT_TOPIC = "/nepi/s2x/sidus_ss400/idx/color_2d_image"
#IMAGE_INPUT_TOPIC = "/nepi/s2x/onwote_hd_poe/idx/color_2d_image"

###!!!!!!!! Set Automation action parameters !!!!!!!!
SAVE_DURATION_S = 5.0 # Seconds. Length of time to save data
SAVE_DATA_MAX_RATE_HZ = 1.0
SAVE_RESET_DELAY_S = 5.0 # Seconds. Delay before starting over search/save process
SAVE_FOLDER_NAME = "snapshot_event/" # Use "" to ignore
SAVE_FILE_PREFIX = "snapshot_event" # Use "" to ignore
SAVE_IMAGE_TYPE = "jpg"

# NEPI ROS namespace setup
NEPI_BASE_NAMESPACE = "/nepi/s2x/"
### Snapshot Topic Name
SNAPSHOT_TOPIC = NEPI_BASE_NAMESPACE + "snapshot_event"
# NEPI Get NAVPOSE Solution Service Name
NAVPOSE_SERVICE_NAME = NEPI_BASE_NAMESPACE + "nav_pose_query"


#####################################################################################
# Globals
#####################################################################################
save_folder = "/mnt/nepi_storage/data/" + SAVE_FOLDER_NAME
save_data_min_interval_s = float(1.0)/SAVE_DATA_MAX_RATE_HZ
save_data_enable = False
last_save_time_s = None

#####################################################################################
# Methods
#####################################################################################

### System Initialization processes
def initialize_actions():
  global save_folder
  print("")
  print("Starting Initialization")  
  # Wait for image topic to exist
  print("Waiting for image topic")  
  wait_for_topic(IMAGE_INPUT_TOPIC, 'sensor_msgs/Image')
  print("Image topic found")
  # Create save folder if needed
  print("Checking Save Folder")
  Save_Folder_Exist = os.path.exists(save_folder)
  if not Save_Folder_Exist:
    print("Creating save folder")
    access = 0o755
    os.makedirs(save_folder,access)
  else:
    print("Save folder exists")
  print("Initialization Complete")
  print("Waiting for snapshot event trigger topic to publish on:")
  print(SNAPSHOT_TOPIC)
  

# Action upon detection of snapshot event trigger
def snapshot_event_callback(event):
  global save_data_enable
  # Start saving data
  print("Enabling data saving")
  save_data_enable = True
  print("Saving for " + str(SAVE_DURATION_S) + " secs")
  time.sleep(SAVE_DURATION_S)
  print("Disabling data saving")
  save_data_enable = False
  # Delay next trigger
  print("Delaying next trigger for " + str(SAVE_RESET_DELAY_S) + " secs")
  time.sleep(SAVE_RESET_DELAY_S)
  print("Waiting for next snapshot event trigger")


### Callback to save images
def image_saver_callback(img_msg):
  global save_data_enable
  global save_data_min_interval_s
  global last_save_time_s
  global save_folder
  if save_data_enable:
    if last_save_time_s is None:
      last_save_time_s =  time.time() - save_data_min_interval_s - 1
    timer = time.time()- last_save_time_s
    if timer > save_data_min_interval_s: # Save Image
      #Convert image from ros to cv2
      bridge = CvBridge()
      cv_image = bridge.imgmsg_to_cv2(img_msg, "bgr8")
      # Saving image to file type
      dt_str=datetime.utcnow().strftime('%Y%m%d-%H%M%S%f')[:-3]
      image_filename=save_folder + SAVE_FILE_PREFIX + '_' + dt_str + '.' + SAVE_IMAGE_TYPE
      print("Saving image to file")
      print(image_filename)
      cv2.imwrite(image_filename,cv_image)
      if SAVE_NAVPOSE_DATA_ENABLED: # Save a NavPose JSON file with image     
        #Get Current Lat, Long, Alt, Heading
        if not rospy.is_shutdown():
          # Get current NEPI NavPose data from NEPI ROS nav_pose_query service call
          try:
            get_navpose_service = rospy.ServiceProxy(NAVPOSE_SERVICE_NAME, NavPoseQuery)
            nav_pose_response = get_navpose_service(NavPoseQueryRequest())
            #print(nav_pose_response)
            # Set current navpose
            current_navpose = nav_pose_response.nav_pose
            # Get current location vector (lat, long, alt) in geopoint data with AMSL height
            fix_amsl = nav_pose_response.nav_pose.fix
            # Set current heading in degrees
            current_heading_deg = nav_pose_response.nav_pose.heading.heading
            # Data to be written
            navpose_data = {
                "Latitude": fix_amsl.latitude,
                "Longitude": fix_amsl.longitude,
                "Heading": current_heading_deg,
             }
            # Serializing json
            json_object = json.dumps(navpose_data, indent=2)
            # Writing to sample.json
            navpose_filename=save_folder + SAVE_FILE_PREFIX + '_' + dt_str + '.nav'
            print("Saving nav to file")
            print(navpose_filename)
            with open(navpose_filename, "w") as outfile:
                outfile.write(json_object)
          except rospy.ServiceException as e:
            print("NavPose service call failed: %s"%e)
            time.sleep(1)


      
      last_save_time_s =  time.time() # Reset last save time
  else:
    last_save_time = None
    

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
  print("Shutting down: Executing script cleanup actions")
  time.sleep(.1)

### Script Entrypoint
def startNode():
  rospy.loginfo("Starting Snapshot Event Detect and Save automation script", disable_signals=True) # Disable signals so we can force a shutdown
  rospy.init_node(name="snapshot_event_detect_save_auto_script")
  # Run Initialization processes
  initialize_actions()
  # Start image saver callback
  rospy.Subscriber(IMAGE_INPUT_TOPIC, Image, image_saver_callback, queue_size = 1)
  # Set up snapshot event callback
  rospy.Subscriber(SNAPSHOT_TOPIC, Empty, snapshot_event_callback, queue_size = 1)
  #Set up cleanup on node shutdown
  rospy.on_shutdown(cleanup_actions)
  # Spin forever (until object is detected)
  rospy.spin()


#####################################################################################
# Main
#####################################################################################

if __name__ == '__main__':
  startNode()

