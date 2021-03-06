#!/usr/bin/env python
'''
Node to determine deviation from trajectory.

'''

import rospy
import numpy as np
import std_msgs

from dynamic_reconfigure.server import Server
from circular_mpc.cfg import dist_finder_mocapConfig

from trajectory_planner import Path

from slip_control_communications.msg import pose_and_references
from slip_control_communications.msg import mocap_data

pub = rospy.Publisher('pose_and_references_topic', pose_and_references, queue_size=1)
path = Path()

# The reference trajectory
circle = path.get_points()

# And the coordinates of its center, and its radius as well.
circle_center_and_radius = path.get_center_and_radius()

circle_x_0 = circle_center_and_radius[0]
circle_y_0 = circle_center_and_radius[1]
circle_r = circle_center_and_radius[2]

# The coordinates of the vehicle at the previous sampling time
previous_x = None
previous_y = None

# The timestamp of the last message received. Will be needed in calculating
# the actual sampling time, that is, the time between two consecutive
# callbacks
timestamp_last_message = None

# The horizon. Make sure that this number is larger than the horizon
# in the predictive controller script
N = 20


#-------------------------------------------------------------------------------
# Given the coordinates of a point (in this case the vehicle V) at x_v and y_v,
# and the coordinates of the center (x_c, y_c) of a circle and its radius (r),
# find point X where the tangent at point X passes through point V
# For visualization see http://jsfiddle.net/zxqCw/1/
#-------------------------------------------------------------------------------
def get_tangent_point(x_v, y_v, x_c, y_c, r):
    dx = x_v - x_c
    dy = y_v - y_c
    dd = np.sqrt(dx**2 + dy**2)


    # The vehicle is outside or on the circle
    if dd >= r:

        a = np.arcsin(r / dd)
        b = np.arctan2(dy, dx)

        t = b + np.pi/2 - a

        tan_point_x = x_c + r * np.cos(t)
        tan_point_y = y_c + r * np.sin(t)

    # The vehicle is inside the circle: there is no tangent
    else:

        tan_point_x = x_v
        tan_point_y = y_v


    ret_list = []
    ret_list.append(tan_point_x)
    ret_list.append(tan_point_y)
    return ret_list


#-------------------------------------------------------------------------------
# A function to get the reference points for the optimization problem
#-------------------------------------------------------------------------------
def get_reference_points(state, ts, method):

    min_dist = 1000.0
    ref_point = None

    # The array of references. Each is a separate point on the circle,
    # each ahead from the previous, starting from ref_point.
    # These will be the points the vehicle will have to plan to pass while
    # running the prediction equations
    refs_x = []
    refs_y = []
    refs_v = []
    refs_psi = []


    if method == 1 or method == 2:
        # Tangent method
        if method == 1:
            # Find the point that connects the vehicle to the circle.
            # This point is tangent to the circle, and this tangent passes through
            # the position of the vehicle.
            tan_point_list = get_tangent_point(state.x, state.y, circle_x_0, circle_y_0, circle_r)

            point_x = tan_point_list[0]
            point_y = tan_point_list[1]

        # min method
        elif method == 2:
            point_x = state.x
            point_y = state.y


        # Find the closest point that lies ON the trajectory
        for point in circle:
            dist = np.sqrt((point_x - point[0])**2 + (point_y - point[1])**2)
            if dist < min_dist:
                min_dist = dist
                ref_point = point

        # The index of the tangent point in the circle list.
        # Based on this, the index of the next references will be calculated.
        tan_index = circle.index(ref_point)

        # Find the references on the circle.
        for i in range(1,N+1):

            # The index of the i-th reference in the circle list
            t = tan_index + np.degrees(state.v / circle_r * ts * i * H)

            while t > 359:
                t = t - 360

            t = int(np.ceil(t))

            # The actual i-th reference point
            ith_ref_point = circle[t]

            x = ith_ref_point[0]
            y = ith_ref_point[1]
            t = ith_ref_point[2]

            while state.psi > 0 and t < 0:
                t = t + 2*np.pi

            refs_x.append(x)
            refs_y.append(y)
            refs_v.append(state.v)
            refs_psi.append(t)

    if method == 3:

        # Find the point that connects the vehicle to the circle.
        # This point is tangent to the circle, and this tangent passes through
        # the position of the vehicle.
        tan_point_list = get_tangent_point(state.x, state.y, circle_x_0, circle_y_0, circle_r)

        point_x = tan_point_list[0]
        point_y = tan_point_list[1]

        # Find the closest point that lies ON the trajectory
        for point in circle:
            dist = np.sqrt((point_x - point[0])**2 + (point_y - point[1])**2)
            if dist < min_dist:
                min_dist = dist
                ref_point = point

        if state.psi > 0 and ref_point[2] < 0:
            ref_point[2] = ref_point[2] + 2*np.pi

        dx = state.x - ref_point[0]
        dy = state.y - ref_point[1]
        dd = np.sqrt(dx**2 + dy**2)

        for i in range(0,N+1):
            x = state.x + i * dd / N * np.cos(ref_point[2])
            y = state.y + i * dd / N * np.sin(ref_point[2])

            refs_x.append(x)
            refs_y.append(y)
            refs_v.append(state.v)
            refs_psi.append(ref_point[2])



    return list([refs_x, refs_y, refs_v, refs_psi])


#-------------------------------------------------------------------------------
# callback
#
# INPUT:
#   state: measurements derived from mocap
#-------------------------------------------------------------------------------
def callback(state):

    global previous_x
    global previous_y
    global timestamp_last_message

    # Update the (not necessarily constant) sampling time
    if timestamp_last_message == None:
        ts = 0.1
    else:
        ts =  rospy.Time.now() - timestamp_last_message
        ts = ts.to_sec()

    timestamp_last_message = rospy.Time.now()


    # MEASURE the velocity of the vehicle. Ideally this would come from a
    # Kalman filter.
    if previous_x is not None:
        vel = np.sqrt((state.x - previous_x)**2 + (state.y - previous_y)**2) / ts
    else:
        vel = 0.0

    # Create the message that is to be sent to the mpc controller,
    # pack all relevant information and publish it
    msg = pose_and_references()

    msg.x = state.x
    msg.y = state.y
    msg.v = vel
    msg.psi = np.radians(state.yaw)

    # The method for finding the point which the references
    # will be built upon.
    method = 1

    # Find the references
    refs_list = get_reference_points(msg, ts, method)

    # The array of references. Each is a separate point on the circle,
    # each ahead from the previous, starting from ref_point.
    # These will be the points the vehicle will have to plan to pass while
    # running the prediction equations
    msg.refs_x = refs_list[0]
    msg.refs_y = refs_list[1]
    msg.refs_v = refs_list[2]
    msg.refs_psi = refs_list[3]

    msg.ts = ts

    pub.publish(msg)

    previous_x = state.x
    previous_y = state.y



#-------------------------------------------------------------------------------
# Callback for dynamically reconfigurable parameters
#-------------------------------------------------------------------------------
def dynamic_reconfigure_callback(config, level):

    global H

    H = config.H

    return config


#-------------------------------------------------------------------------------
# main
#-------------------------------------------------------------------------------
if __name__ == '__main__':
    rospy.init_node('dist_finder_mocap_node', anonymous=True)
    rospy.loginfo("[Node] dist_finder_mocap_node started")

    rospy.Subscriber("car_state_topic", mocap_data, callback, queue_size=1)
    dynamic_reconfigure_server = Server(dist_finder_mocapConfig, dynamic_reconfigure_callback)
    rospy.spin()
