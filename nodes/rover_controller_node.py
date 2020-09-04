#!/usr/bin/env python

import rospy
import math
from geometry_msgs.msg import Twist, Pose, PoseStamped, Point
from leo_rover_localization.srv import GetPathFromMap, GetPathFromMapRequest
from leo_rover_localization.srv import SetMotorEnable
from leo_rover_localization.srv import SwitchWaypoint, SwitchWaypointRequest
from leo_rover_localization.srv import SetNewTarget
from nav_msgs.msg import Odometry

def Quad2Euler(q):
    """
    This function transforms from quernion to euler

    #Quaternion_to_Euler_Angles_Conversion
    For details, see https://en.wikipedia.org/wiki/Conversion_between_quaternions_and_Euler_angles

    Parameters
    ----------
    q : Pose().orientation
        This is an orientation vector in queternion form

    Returns
        The euler form of the parameter q
    -------
    int
        Description of return value
    """
    # roll (x-axis rotation)
    sinr_cosp = 2 * (q.w * q.x + q.y * q.z)
    cosr_cosp = 1 - 2 * (q.x * q.x + q.y * q.y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # pitch (y-axis rotation)
    sinp = 2 * (q.w * q.y - q.z * q.x)
    if (abs(sinp) >= 1):
        # use 90 degrees if out of range
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    # yaw (z-axis rotation)
    siny_cosp = 2 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    # Transform the q of the form PoseStamped().pose.orientation to angle
    # by applying atan2(y,x) => float angle from math library.
    return (roll, pitch, yaw)


def update_position(msg, rover):
    rover.position.x = msg.position.x
    rover.position.y = msg.position.y
    rover.position.z = msg.position.z
    rover.orientation.x = msg.orientation.x
    rover.orientation.y = msg.orientation.y
    rover.orientation.z = msg.orientation.z
    rover.orientation.w = msg.orientation.w

def rover_pose_update(msg, rover):
    rover = msg.pose.pose
    rover.position.y *= -1

def handle_target_point(msg):
    global target_point
    target_point = msg.target
    return True

def handle_motor_enable(msg):
    global is_enable
    global pub
    is_enable = msg.enable
    
    if is_enable:
        return "motors are enabled, Don't panic!"
    else:
        pub.publish(Twist())
        return "motors are disabled."

if __name__ == '__main__':
    target = Pose()
    rover = Pose()
    path = Point()
    is_enable = False
    dist = -1
    u_max = 0.5
    K_p = 0.5

    # initialize node
    rospy.init_node('rover_controller', anonymous=True)

    # publish /cmd_vel to drive rover and
    # initialize its message container
    pub = rospy.Publisher('cmd_vel', Twist, queue_size=10)
    msg = Twist()
    
    rover = Odometry().pose.pose
    target_point = Point(0, 0, 0)
        
    # wait until the service point creator to get the next action
    # is ready and get a proxy of it
    rospy.loginfo_once('[rover_controller] is waiting... /get_path_from_map')
    rospy.wait_for_service('/get_path_from_map')

    srv4GetPath = rospy.ServiceProxy('get_path_from_map', GetPathFromMap)
    srv4switchWps = rospy.ServiceProxy('get_next_waypoint', SwitchWaypoint)

    rospy.Service('set_waypoint', SetNewTarget, handle_target_point)
    rospy.Service('enable_motors', SetMotorEnable, handle_motor_enable)


    # subscribe the topic /odometry/filtered to learn local position of the rover
    rospy.Subscriber('/odometry/filtered', Odometry, rover_pose_update, rover)

    rate = rospy.Rate(10)  # 10 Hz

    while not rospy.is_shutdown():

        rospy.loginfo(
            '[rover_controller] is requesting... /get_path_from_map')
        

        rover_point = Point(rover.position.x, rover.position.y, 0)

        if dist == -1:
            req4GetPath = GetPathFromMapRequest(rover_point, target_point)
            res4path = srv4GetPath(req4GetPath) ## bool
            req4switchWps = SwitchWaypointRequest(True)
            res4switchWps = srv4switchWps(req4switchWps)
        elif dist < 5:
            req4switchWps = SwitchWaypointRequest(True)
            res4switchWps = srv4switchWps(req4switchWps)

        if res4switchWps.is_finished and is_enable:
            rospy.logwarn('rover is near destination...')
            rospy.logwarn('please set another waypoint...')
            is_enable = False
        elif is_enable:
            dist = math.sqrt((res4switchWps.new_wp.x - rover.position.x) **
                         2 + (res4switchWps.new_wp.y - rover.position.y)**2)


            alpha = math.atan2(res4switchWps.new_wp.y - rover.position.y,
                            res4switchWps.new_wp.x - rover.position.x)
            alpha_cur = Quad2Euler(rover.orientation)[2]

            dot_product = (math.cos(alpha) * math.cos(alpha_cur) +
                        math.sin(alpha) * math.sin(alpha_cur))

            msg.linear.x = dot_product * u_max if dot_product > 0 else 0
            msg.angular.z = (alpha_cur - alpha) * K_p
            
            pub.publish(msg)

        rate.sleep()