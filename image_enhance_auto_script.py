#!/usr/bin/env python

__author__ = "Jason Seawall"
__copyright__ = "Copyright 2023, Numurus LLC"
__email__ = "nepi@numurus.com"
__credits__ = ["Jason Seawall", "Josh Maximoff"]

__license__ = "GPL"
__version__ = "2.0.4.0"


# Sample NEPI Automation Script. 
# Uses onboard ROS python library to
# 1. run sensor imagery through an image enhancement algorithm and republish to a new topic
# 2. Run until Stopped

import time
import sys
import rospy
import numpy as np
import cv2

from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from std_msgs.msg import UInt8, Empty, String, Bool

#####################################################################################
# SETUP - Edit as Necessary ##################################
##########################################

###!!!!!!!! Set Image ROS Topic Name to Use  !!!!!!!!
IMAGE_INPUT_TOPIC = "/nepi/s2x/nexigo_n60_fhd_webcam_audio/idx/color_2d_image"
#IMAGE_INPUT_TOPIC = "/nepi/s2x/see3cam_cu81/idx/color_2d_image"
#IMAGE_INPUT_TOPIC = "/nepi/s2x/sidus_ss400/idx/color_2d_image"
#IMAGE_INPUT_TOPIC = "/nepi/s2x/onwote_hd_poe/idx/color_2d_image"
#IMAGE_INPUT_TOPIC = "/nepi/s2x/zed2/zed_node/left/image_rect_color"

ENHANCE_SENSITIVITY_RATIO = 0.5

# ROS namespace setup
NEPI_BASE_NAMESPACE = "/nepi/s2x/"

IMAGE_OUTPUT_TOPIC = NEPI_BASE_NAMESPACE + "image_enhanced"

#####################################################################################
# Globals
#####################################################################################
enhanced_image_pub = rospy.Publisher(IMAGE_OUTPUT_TOPIC, Image, queue_size=10)

#####################################################################################
# Methods
#####################################################################################

### System Initialization processes
def initialize_actions():
  print("")
  print("Starting Initialization")  
  # Wait for topic
  print("Waiting for topic: " + IMAGE_INPUT_TOPIC)
  wait_for_topic(IMAGE_INPUT_TOPIC, 'sensor_msgs/Image')
  print("Initialization Complete")


### callback to get image, enahance image, and publish new image on new topic
def image_enhance_callback(img_msg):
  global ehnanced_image_pub
  #Convert image from ros to cv2
  bridge = CvBridge()
  cv_image = bridge.imgmsg_to_cv2(img_msg, "bgr8")
  # Get contours
  cv_image.setflags(write=1)
  # Color Correction optimization
  Max=[0,0,0]
  for k in range(0, 3):
    Max[k] = np.max(cv_image[:,:,k])
  Min_Max_channel  = np.min(Max)
  for k in range(0, 3):
    Max_channel  = np.max(cv_image[:,:,k])
    Min_channel  = np.min(cv_image[:,:,k])
    Mean_channel = np.mean(cv_image[:,:,k])
    Chan_scale = (255 - Mean_channel) / (Max_channel - Min_channel)
    if Chan_scale < 1:
      Chan_scale = 1 - (1-Chan_scale)*(255-Min_Max_channel)/170
    elif Chan_scale > 1:
      Chan_scale = 1 + (Chan_scale-1)*(255-Min_Max_channel)/170
    if Chan_scale > 1*(1+ENHANCE_SENSITIVITY_RATIO):
      Chan_scale = 1 *(1+ENHANCE_SENSITIVITY_RATIO)
    if Chan_scale < -1*(1+ENHANCE_SENSITIVITY_RATIO):
      Chan_scale = -1 *(1+ENHANCE_SENSITIVITY_RATIO)
    Chan_offset = -1*Min_channel
    if Chan_offset < -10 * (1+9*ENHANCE_SENSITIVITY_RATIO):
      Chan_offset = -10 * (1+9*ENHANCE_SENSITIVITY_RATIO)
  cv_image[:,:,k] = (cv_image[:,:,k] + Chan_offset) * Chan_scale
  # Contrast and Brightness optimization
  gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
  # Calculate grayscale histogram
  hist = cv2.calcHist([gray],[0],None,[256],[0,256])
  hist_size = len(hist)
  # Calculate cumulative distribution from the histogram
  accumulator = []
  accumulator.append(float(hist[0]))
  for index in range(1, hist_size):
    accumulator.append(accumulator[index -1] + float(hist[index]))
  # Locate points to clip
  maximum = accumulator[-1]
  clip_hist_percent = (maximum/100.0)
  clip_hist_percent /= 2.0
  # Locate left cut
  minimum_gray = 0
  while accumulator[minimum_gray] < clip_hist_percent:
    minimum_gray += 5
  # Locate right cut
  maximum_gray = hist_size -1
  while accumulator[maximum_gray] >= (maximum - clip_hist_percent):
    maximum_gray -= 1
  # Calculate alpha and beta values
  alpha = 255 / (maximum_gray - minimum_gray) * (0.5+ENHANCE_SENSITIVITY_RATIO)
  if alpha>2: ##
    alpha=2 ##
  beta = (-minimum_gray * alpha + 10) * (0.5+ENHANCE_SENSITIVITY_RATIO)
  if beta<-50: ##
    beta=-50 ##
  cv_image = cv2.convertScaleAbs(cv_image, alpha=alpha, beta=beta)
  img_enhc_msg = bridge.cv2_to_imgmsg(cv_image,"bgr8")#desired_encoding='passthrough')
  # Publish Enahaced Image Topic
  if not rospy.is_shutdown():
    enhanced_image_pub.publish(img_enhc_msg) # You can view the enhanced_2D_image topic at //192.168.179.103:9091/ in a connected web browser

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
  global enhanced_image_pub
  print("Shutting down: Executing script cleanup actions")
  # Unregister publishing topics
  enhanced_image_pub.unregister()

### Script Entrypoint
def startNode():
  rospy.loginfo("Starting Image Enhance automation script", disable_signals=True) # Disable signals so we can force a shutdown
  rospy.init_node
  rospy.init_node(name="image_enhance_auto_script")
  # Run Initialization processes
  initialize_actions()
  # Start image enhance process and pubslisher
  rospy.Subscriber(IMAGE_INPUT_TOPIC, Image, image_enhance_callback, queue_size = 1)
  #Set up cleanup on node shutdown
  rospy.on_shutdown(cleanup_actions)
  # Spin forever (until object is detected)
  rospy.spin()


#####################################################################################
# Main
#####################################################################################

if __name__ == '__main__':
  startNode()

