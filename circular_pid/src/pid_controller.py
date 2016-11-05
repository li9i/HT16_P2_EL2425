#!/usr/bin/env python
'''
Node for PID control.

'''

import rospy
import numpy as np
from f1tenth_msgs.msg import drive_param
from f1tenth_msgs.msg import pid_input
from f1tenth_msgs.msg import mocap_data

sim_rate = 10
kp = 1.1
ki = 0.01
kd = 0.5
prev_angle_error = None
integral_error = 0.0
angle = 0.0

pub = rospy.Publisher('drive_parameters', drive_param, queue_size=1)

def control(data):
	global prev_angle_error
	global integral_error
	global kp
	global ki
	global kd
	global angle

	## Your code goes here
	# 1. Scale the error
	# 2. Apply the PID equation on error
	# 3. Make sure the error is within bounds

	angle_error = data.pid_error

	if prev_angle_error == None:
		delta_error = 0
	else:
		delta_error = angle_error - prev_angle_error

	prev_angle_error = angle_error
	integral_error += angle_error
	if abs(angle_error) < 0.01:
		integral_error = 0.

	angle = kp*angle_error + kd*delta_error*sim_rate + ki*integral_error/sim_rate #- kd*delta_error*sim_rate

	# Limit angle command between steering angle limits
	while angle > np.pi/3:
		angle = np.pi/3
	while angle < -np.pi/3:
		angle = -np.pi/3

	## END
	msg = drive_param();
	msg.velocity = data.pid_vel
	msg.angle = angle
	pub.publish(msg)

if __name__ == '__main__':
	print("Listening to error")
	rospy.init_node('pid_controller', anonymous=True)
	rospy.Subscriber("error", pid_input, control)
	rospy.spin()