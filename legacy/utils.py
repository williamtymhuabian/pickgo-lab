import rospy 
from sensor_msgs.msg import Image , CameraInfo
from geometry_msgs.msg import TransformStamped,PoseStamped
import cv2 
from cv_bridge import CvBridge
import numpy as np 
import math
import tf
import threading
import time
from demo.srv import robot_move
from demo.msg import pose
from grap import serial_init , grap_init,grap_catch,grap_release
import ctypes 

# import Arm1_server_M1_for_log 
# from Arm1_server_M1_for_log import update_image_cb_to_none,grab_back_switch_case,get_action_value,get_grab_pre_point,Log_Arm1_server_print
from Arm1_server_M1_for_log import Log_Arm1_server_print
#===============================================================MODIFY

import datetime
import os
from PIL import Image
color_dict = {}
color_list = []
hsv_mask_list = []
#-----------------------------------------------------------------------------------------------------------SPEED_TABLE>>>
speed_table={
    "go_home_speed":100,
    "go_inflection_speed":100,
    "go_target_speed":100,
    "back_target_speed":100,
    "rotate_angle_speed":100,
    "move_to_center_speed":100,
}
#-----------------------------------------------------------------------------------------------------------TARGET_TABLE>>>
grab_target_table = {
    'arm1-1-1': [297.787, -325.616, 670.058, -89.181, -0.486, -137.505, 50],
    'arm1-1-2': [297.787, -325.616, 670.058, -89.181, -0.486, -137.505, 50],
    'arm1-1-3': [297.787, -325.616, 670.058, -89.181, -0.486, -137.505, 50],
    'arm1-1-4': [297.787, -325.616, 670.058, -89.181, -0.486, -137.505, 50],
    'arm1-1-5': [297.787, -325.616, 670.058, -89.181, -0.486, -137.505, 50],
    'arm1-2-1': [360.009, -364.077, 462.079, -125.779, 0.712, -133.868, 50],
    'arm1-2-2': [360.009, -364.077, 462.079, -125.779, 0.712, -133.868, 50],
    'arm1-2-3': [360.009, -364.077, 462.079, -125.779, 0.712, -133.868, 50],
    'arm1-2-4': [360.009, -364.077, 462.079, -125.779, 0.712, -133.868, 50],
    'arm1-2-5': [360.009, -364.077, 462.079, -125.779, 0.712, -133.868, 50],
    'arm1-3-1': [292.358, -354.835, 61.116, -123.169, -1.433, -137.049, 50],
    'arm1-3-2': [292.358, -354.835, 61.116, -123.169, -1.433, -137.049, 50],
    'arm1-3-3': [292.358, -354.835, 61.116, -123.169, -1.433, -137.049, 50],
    'arm1-3-4': [292.358, -354.835, 61.116, -123.169, -1.433, -137.049, 50],
    'arm1-3-5': [292.358, -354.835, 61.116, -123.169, -1.433, -137.049, 50],
    'arm1robot01': [-131.616, 352.766, 368.439, -178.767, -0.336, 39.426, 50],
    'arm1robot02': [-355.567, 145.225, 370.057, -177.975, -2.927, 129.085, 50],
    'arm1robot03': [-268.467, 483.106, 357.348, -177.229, -2.137, 44.453, 50],
    'arm1robot04': [-491.788, 284.279, 368.439, 179.192, -3.057, 45.628, 50],
    'arm2robot01': [542.93, -368.004, 170.668, 175.469, 0.965, -133.789, 50],
    'arm2robot02': [344.488, -545.483, 170.668, -179.975, -1.957, -137.874, 50],
    'arm2robot03': [441.794, -245.754, 170.668, -178.959, 0.037, -136.189, 50],
    'arm2robot04': [216.319, -428.779, 170.668, 178.405, -0.593, -137.736, 50],
    'arm2belt01': [516.995, 265.819, 385.029, 178.406, 0.329, -136.163, 50],
    'arm2belt02': [-306.129, -513.479, 385.011, -179.207, 0.422, -135.742, 50]
}

loosen_target_table = {
    'arm1-1-1': [492.987, -486.749, 697.369, -87.166, 1.779, -136.289, 50],
    'arm1-1-2': [492.987, -486.749, 697.369, -87.166, 1.779, -136.289, 50],
    'arm1-1-3': [492.987, -486.749, 697.369, -87.166, 1.779, -136.289, 50],
    'arm1-1-4': [492.987, -486.749, 697.369, -87.166, 1.779, -136.289, 50],
    'arm1-1-5': [492.987, -486.749, 697.369, -87.166, 1.779, -136.289, 50],
    'arm1-2-1': [498.259, -489.499, 348.568, -94.869, -0.018, -138.058, 50],
    'arm1-2-2': [498.259, -489.499, 348.568, -94.869, -0.018, -138.058, 50],
    'arm1-2-3': [498.259, -489.499, 348.568, -94.869, -0.018, -138.058, 50],
    'arm1-2-4': [498.259, -489.499, 348.568, -94.869, -0.018, -138.058, 50],
    'arm1-2-5': [498.259, -489.499, 348.568, -94.869, -0.018, -138.058, 50],
    'arm1-3-1': [480.428, -515.959, -1.229, -119.689, 0.027, -130.785, 50],
    'arm1-3-2': [480.428, -515.959, -1.229, -119.689, 0.027, -130.785, 50],
    'arm1-3-3': [480.428, -515.959, -1.229, -119.689, 0.027, -130.785, 50],
    'arm1-3-4': [480.428, -515.959, -1.229, -119.689, 0.027, -130.785, 50],
    'arm1-3-5': [480.428, -515.959, -1.229, -119.689, 0.027, -130.785, 50],
    'arm1robot01': [-138.629, 357.543, 140, -179.764, -0.222, 45.291, 50],
    'arm1robot02': [-365.938, 186.548, 140.772, 177.759, 2.351, 48.524, 50],
    'arm1robot03': [-298.364, 504.829, 140, -178.289, 0.22, 39.334, 50],
    'arm1robot04': [-506.809, 296.366, 142.673, 178.657, -3.025, 45.674, 50],
    'arm2robot01': [628.454, -422.335, 26.259, -179.01, -1.589, -134.063, 50],
    'arm2robot02': [411.262, -634.519, 30.233, -178.195, 0.696, -135.17, 50],
    'arm2robot03': [485.456, -277.013, 27.623, -178.475, -1.477, -133.934, 50],
    'arm2robot04': [273.579, -484.129, 40.358, -178.745, -0.864, -136.657, 50],
    'arm2belt01': [597.995, 191.819, 235.029, 178.406, 0.329, -136.163, 50],
    'arm2belt02': [-233.869, -598.015, 239.704, 178.729, -1.479, -134.633, 50]
}

#-----------------------------------------------------------------------------------------------------------DAYLIGHT_COLOR_RANGES>>>
col_dict_daylight_robot = {

    "col_dict_daylight_robotred": {"hsv_l": np.array([0, 60, 60]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_daylight_robotorange": {"hsv_l": np.array([4, 100, 100]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_daylight_robotyellow": {"hsv_l": np.array([20, 100, 90]), "hsv_h": np.array([28, 255, 255])},
    "col_dict_daylight_robotgreen": {"hsv_l": np.array([30, 50, 70]), "hsv_h": np.array([55, 255, 220])}, #g12
    "col_dict_daylight_robotcyan": {"hsv_l": np.array([86,40,70]), "hsv_h": np.array([111,111,255])},
    "col_dict_daylight_robotblue": {"hsv_l": np.array([96,80,20]), "hsv_h": np.array([116,255,230])},
    "col_dict_daylight_robotpurple": {"hsv_l": np.array([116,50, 0]), "hsv_h": np.array([153, 255, 255])},
    "col_dict_daylight_robotpink": {"hsv_l": np.array([159, 71, 124]), "hsv_h": np.array([180, 200, 200])}, ###wangwei 12.20
 
}

col_dict_daylight_shelf_1 = {
    "col_dict_daylight_shelf_1red": {"hsv_l": np.array([0, 70, 60]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_daylight_shelf_1orange": {"hsv_l": np.array([4, 50, 50]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_daylight_shelf_1yellow": {"hsv_l": np.array([20, 69, 44]), "hsv_h": np.array([28, 255, 255])},
    "col_dict_daylight_shelf_1green": {"hsv_l": np.array([30, 40, 60]), "hsv_h": np.array([57, 255, 255])},
    "col_dict_daylight_shelf_1cyan": {"hsv_l": np.array([86,35,40]), "hsv_h": np.array([111,150,255])},
    "col_dict_daylight_shelf_1blue": {"hsv_l": np.array([96,60,50]), "hsv_h": np.array([116,255,230])},
    "col_dict_daylight_shelf_1purple": {"hsv_l": np.array([116,50, 50]), "hsv_h": np.array([153, 255, 255])},
    "col_dict_daylight_shelf_1pink": {"hsv_l": np.array([156, 50, 84]), "hsv_h": np.array([180, 214, 255])},

}
col_dict_daylight_shelf_23 = {
    "col_dict_daylight_shelf_23red": {"hsv_l": np.array([0, 70, 60]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_daylight_shelf_23orange": {"hsv_l": np.array([4, 50, 50]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_daylight_shelf_23yellow": {"hsv_l": np.array([20, 75, 31]), "hsv_h": np.array([28, 255, 255])},
    "col_dict_daylight_shelf_23green": {"hsv_l": np.array([30, 50, 30]), "hsv_h": np.array([50, 255, 255])},
    "col_dict_daylight_shelf_23cyan": {"hsv_l": np.array([80,30,30]), "hsv_h": np.array([116,150,255])},
    "col_dict_daylight_shelf_23blue": {"hsv_l": np.array([96,60,20]), "hsv_h": np.array([116,255,230])},
    "col_dict_daylight_shelf_23purple": {"hsv_l": np.array([116,50, 0]), "hsv_h": np.array([153, 255, 255])},
    "col_dict_daylight_shelf_23pink": {"hsv_l": np.array([160, 71, 74]), "hsv_h": np.array([180, 200, 255])},
}


#-----------------------------------------------------------------------------------------------------------NIGHT_COLOR_RANGES>>>
col_dict_night_robot = {
    "col_dict_daylight_robotred": {"hsv_l": np.array([0, 60, 60]), "hsv_h": np.array([10, 255, 255])},# no experient at night

    "col_dict_night_robotorange": {"hsv_l": np.array([4, 100, 100]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_night_robotyellow": {"hsv_l": np.array([20, 100, 90]), "hsv_h": np.array([28, 255, 255])},
    "col_dict_night_robotgreen": {"hsv_l": np.array([30, 65, 50]), "hsv_h": np.array([55, 255, 200])},
    "col_dict_night_robotcyan": {"hsv_l": np.array([80,40,70]), "hsv_h": np.array([116,255,255])},
    "col_dict_night_robotblue": {"hsv_l": np.array([96,80,81]), "hsv_h": np.array([116,255,255])},
    "col_dict_night_robotpurple": {"hsv_l": np.array([116, 79, 0]), "hsv_h": np.array([153, 255, 255])},
    "col_dict_night_robotpink": {"hsv_l": np.array([159, 64, 124]), "hsv_h": np.array([180, 220, 200])},
}
col_dict_night_shelf_1 = {
    "col_dict_daylight_shelf_1red": {"hsv_l": np.array([0, 70, 60]), "hsv_h": np.array([10, 255, 255])},# no experient at night
    "col_dict_night_shelf_1orange": {"hsv_l": np.array([4, 50, 50]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_night_shelf_1yellow": {"hsv_l": np.array([20, 69, 44]), "hsv_h": np.array([28, 255, 255])},
    "col_dict_night_shelf_1green": {"hsv_l": np.array([30, 50, 70]), "hsv_h": np.array([60, 220, 230])},
    "col_dict_night_shelf_1cyan": {"hsv_l": np.array([80,50,40]), "hsv_h": np.array([116,255,255])},
    "col_dict_night_shelf_1blue": {"hsv_l": np.array([96,80,0]), "hsv_h": np.array([115,255,230])},
    "col_dict_night_shelf_1purple": {"hsv_l": np.array([116,50, 0]), "hsv_h": np.array([153, 255, 255])},
    "col_dict_night_shelf_1pink": {"hsv_l": np.array([159, 64, 124]), "hsv_h": np.array([180, 220, 230])},
}

col_dict_night_shelf_23 = {
    "col_dict_daylight_shelf_23red": {"hsv_l": np.array([0, 70, 60]), "hsv_h": np.array([10, 255, 255])},# no experient at night
    "col_dict_night_shelf_23orange": {"hsv_l": np.array([4, 50, 50]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_night_shelf_23yellow": {"hsv_l": np.array([20, 75, 31]), "hsv_h": np.array([28, 255, 255])},
    "col_dict_night_shelf_23green": {"hsv_l": np.array([33, 40, 0]), "hsv_h": np.array([72, 255, 255])},
    "col_dict_night_shelf_23cyan": {"hsv_l": np.array([80,30,30]), "hsv_h": np.array([116,255,255])},
    "col_dict_night_shelf_23blue": {"hsv_l": np.array([96,80,0]), "hsv_h": np.array([115,255,230])},
    "col_dict_night_shelf_23purple": {"hsv_l": np.array([116, 50, 0]), "hsv_h": np.array([153, 255, 255])},
    "col_dict_night_shelf_23pink": {"hsv_l": np.array([160, 64, 124]), "hsv_h": np.array([180, 220, 200])},
}

col_dict_day_ship={
    "col_dict_day_ship_red": {"hsv_l": np.array([0, 70, 60]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_day_ship_purple": {"hsv_l": np.array([116, 50, 0]), "hsv_h": np.array([153, 255, 255])},
    # "col_dict_day_ship_green": {"hsv_l": np.array([33, 40, 0]), "hsv_h": np.array([72, 255, 255])},
    "col_dict_day_ship_green": {"hsv_l": np.array([26, 27, 82]), "hsv_h": np.array([72, 255, 255])},
}

col_dict_night_ship={
    "col_dict_night_ship_red": {"hsv_l": np.array([0, 70, 60]), "hsv_h": np.array([10, 255, 255])},
    "col_dict_night_ship_purple": {"hsv_l": np.array([116, 50, 0]), "hsv_h": np.array([153, 255, 255])},
    "col_dict_night_ship_green": {"hsv_l": np.array([26, 27, 82]), "hsv_h": np.array([72, 255, 255])},
}


def get_current_time():
    return datetime.datetime.now().time()

def update_dict(is_robot,is_arm1_1,is_ship):
    global color_dict,hsv_mask_list,color_list
    hsv_mask_list=[]
    color_list = []
    current_time = get_current_time()
    Log_Arm1_server_print("current_time",current_time)
    
    # 8:00-17:00->daytime
    daylight_start = datetime.time(8, 0)
    daylight_end = datetime.time(17, 0)
    
    if daylight_start <= current_time <= daylight_end:
        if is_robot:
            color_dict= col_dict_daylight_robot
        else:
            if is_ship:
                color_dict=col_dict_day_ship
            elif is_arm1_1:
                color_dict= col_dict_daylight_shelf_1
            else:
                color_dict= col_dict_daylight_shelf_23   
    else:
        if is_robot:
            color_dict= col_dict_night_robot
        else:
            if is_ship:
                color_dict=col_dict_night_ship
            elif is_arm1_1:
                color_dict= col_dict_night_shelf_1
            else:
                color_dict= col_dict_night_shelf_23
    Log_Arm1_server_print(color_dict)
    for color, values in color_dict.items():
        color_list.append(color)
        hsv_mask_list.append([values['hsv_l'], values['hsv_h']])
    for hsv_mask_list_value in hsv_mask_list:
        Log_Arm1_server_print(hsv_mask_list_value)



#===============================================================addColor
grab_robot=False
def is_grab_robot(is_robot):
    global grab_robot
    if is_robot:
        grab_robot=1

demo_lib = None
robot_service = None
ser = None

color_det = False
max_try_cnt=10
reach_max_try_cnt=False
img_cnt=0
rotate_ag=False
# blue_mask_l = np.array([97,112,98])
# blue_mask_h = np.array([142,255,255])
det_mask_l = None
det_mask_h = None

run_done = False

def arm_grap_catch():
    time.sleep(0.5)
    grap_catch(ser)
    time.sleep(1.5)

def arm_grap_release():
    time.sleep(0.5)
    grap_release(ser)
    time.sleep(1.5)


def rotate_angle(img):
    global det_mask_l ,det_mask_h , color_det,run_done,max_try_cnt,reach_max_try_cnt
    global rotate_ag
    # rotate_ag=False
    color_det=False
    cv2.imwrite("out.png",img)
    if(max_try_cnt>=0 and not run_done):
        max_try_cnt=max_try_cnt-1
        Log_Arm1_server_print("max_try_cnt",max_try_cnt)
        if not color_det:
            Log_Arm1_server_print('start to det color(in rotate_angle )')
            res = det_color(img)
            if res:
                #Log_Arm1_server_print('test ok')
                det_mask_l = res[0]
                det_mask_h = res[1]
                color_det = True
            else:
                Log_Arm1_server_print('color det failed')
                color_det = False
                return None
        if  not run_done:
            Log_Arm1_server_print("rotate->wait for wait_done sleep 1s")
            # time.sleep(0.2)
            hsv_image = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # add mask
            mask=None
            mask = cv2.inRange(hsv_image, det_mask_l, det_mask_h)
            
            if mask is not None:  
                # Log_Arm1_server_print("Found color:", found_color)      
                res = det_rect(mask) 
                if res:
                    # cv2.drawContours(img,[res[0]],0,(0,0,255),2)
                    # cv2.imshow('rect',img)
                    # cv2.waitKey(1)
                    box_angle = res[3]
                    if abs(box_angle) < 45 :
                        rotate_angle = -abs(box_angle)
                    else:
                        rotate_angle = (90.0 -abs(box_angle))
                    my_pose = pose()
                    my_pose.y = rotate_angle
                    if robot_service :
                        res = robot_service(my_pose,80.0,True)
                        Log_Arm1_server_print('rotate angle,res=',res)
                        if res:
                            run_done = True
                        else:
                            Log_Arm1_server_print('robot move error')
                    else:   
                        exit(0)
    if max_try_cnt<0:
        Log_Arm1_server_print('if max_try_cnt<0')
        reach_max_try_cnt=True
        run_done = True
        rotate_ag=True

     

def move_to_center(img):
    # if(max_try_cnt>=0 and not run_done):
    global det_mask_l ,det_mask_h , color_det,run_done
    if not run_done:
        if not color_det:
            Log_Arm1_server_print('start to det color(in move_to_center )')
            res = det_color(img)
            if res:
                #Log_Arm1_server_print('test ok')
                det_mask_l = res[0]
                det_mask_h = res[1]
                color_det=True
            else:
                Log_Arm1_server_print('color det failed')
                color_det = False
                return None
            # color_det = True
        if  not run_done:
            Log_Arm1_server_print("to_center->wait for wait_done sleep 1s")
            # time.sleep(0.2)
            hsv_image = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask=None
            mask = cv2.inRange(hsv_image, det_mask_l, det_mask_h)
            Log_Arm1_server_print("to_center->before judge mask_nonzero")
               
            if mask is not None:  
                # Log_Arm1_server_print("Found color:", found_color)      
                res = det_rect(mask)  
                if res :
                    Log_Arm1_server_print("detect success")
                    cx = res[1]
                    cy = res[2]
                    diff_x = cx - img.shape[1]/2
                    diff_y = cy - img.shape[0]/2
                    my_pose = pose()
                    if grab_robot:
                        my_pose.rx = (-diff_x /1000)*0.57
                        my_pose.ry = (-diff_y / 1000)*0.6
                    else:
                        my_pose.rx = (-diff_x /1000)
                        my_pose.ry = (-diff_y / 1000)
                    Log_Arm1_server_print("my_pose.ry=",my_pose.ry," ","my_pose.rx=",my_pose.rx)
                    if robot_service :
                        res = robot_service(my_pose,45.0,True)
                        Log_Arm1_server_print("move_to_center:res->",res)
                        run_done = True
                    else:
                        exit(0)
                else:
                    Log_Arm1_server_print("detect failure")

def wait_task(task_id,dest_name):
    #�·�����
    task_id = int(task_id)
    demo_lib.woosh_robot_run_task_group.argtypes = [ctypes.c_int]
    #������id  ��Ҫ�޸�
    task_id = ctypes.c_int(task_id)
    res = demo_lib.woosh_robot_run_task_group(task_id)
    Log_Arm1_server_print(res)


    demo_lib.woosh_robot_listen.argtypes = [ctypes.c_char_p,ctypes.c_char_p]
    #Ŀ������� ��Ҫ�޸�
    dest_name = dest_name
    dest_name = dest_name.encode()
    dest_name = ctypes.c_char_p(dest_name)

    # �����Ƿ񵽵��ȴ�״̬  ���޸�
    dest_state = 'ActionWait'
    dest_state = dest_state.encode()
    dest_state = ctypes.c_char_p(dest_state)

    #����Ŀ��� 123  ״̬wait.  ������״̬Ϊ ��Ŀ���123�ȴ���ʱ�򷵻� --- ����
    demo_lib.woosh_robot_listen(dest_name , dest_state)



def wait_done():
    global run_done,color_det,max_try_cnt
    run_done = False
    while True:
        if run_done:
            # update_image_cb_to_none()
            max_try_cnt=10
            # color_det=False
            return

def det_rect(mask):
    kernel = np.ones((5,5),np.uint8)
    mask = cv2.morphologyEx(mask , cv2.MORPH_OPEN,kernel)
    mask = cv2.morphologyEx(mask , cv2.MORPH_CLOSE,kernel)
    contours,hierarchy = cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    rect = None
    box = 0 
    cx = 0 
    cy = 0
    cnt = max(contours, key=cv2.contourArea)
    (x,y,w,h) = cv2.boundingRect(cnt)
    if w < 35 and h < 35:
        return None
    rect = cv2.minAreaRect(cnt)
    box = cv2.boxPoints(rect)
    cx = np.mean(box[:,0])
    cy = np.mean(box[:,1])
    box = np.int0(box)
    if rect :
        return [box,cx,cy,rect[2]]
    else:
        return None

def debug_img(img):
    global color_det,det_mask_l,det_mask_h
    # if color_det:
    #     hsv_image = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    #     mask = cv2.inRange(hsv_image, det_mask_l, det_mask_l)
    #     res = det_rect(mask)  
    #     if res:
    #         cv2.drawContours(img, [res[0]], 0, (0, 0, 255), 2)
    cv2.imshow('rect', cv2.flip(img,-1))
    # cv2.imshow('mask', found_masks[found_color])
    cv2.waitKey(1)  
   
        
    # # Log_Arm1_server_print("in debug image")
    # hsv_image = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # found_color = None  
    # found_masks = {} 
    # mask_l=None
    # mask_h=None
    # size_threshold = img.shape[0] * img.shape[1] * 0.04
    # for color_name, hsv_range in zip(color_list, hsv_mask_list):
    #     mask_l, mask_h = hsv_range
    #     mask = cv2.inRange(hsv_image, mask_l, mask_h)
    #     mask_nonzero=np.count_nonzero(mask==255) 
    #     # Log_Arm1_server_print("{color_name}_mask_nonzero=",mask_nonzero)
    #     # Log_Arm1_server_print("size_threshold=",size_threshold)
    #     if mask_nonzero > size_threshold:
    #         found_color = color_name 
    #         found_masks[found_color] = mask  
    #         break  
    # img1=img.copy()
    # if found_color is not None:  
    #     # Log_Arm1_server_print("Found color:", found_color)
    #     res = det_rect(found_masks[found_color])  
    #     if res:
    #         cv2.drawContours(img1, [res[0]], 0, (0, 0, 255), 2)
    # cv2.imshow('rect', cv2.flip(img1,-1))
    # # cv2.imshow('mask', found_masks[found_color])
    # cv2.waitKey(1)  
    # # else:
    # #     Log_Arm1_server_print("Func->debug_img:No color found")


       
    

def det_color(img):
    hsv_image = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    found_color = None  
    found_masks = {} 
    mask_l=None
    mask_h=None
    size_threshold = img.shape[0] * img.shape[1] * 0.04
    Log_Arm1_server_print("in det color",hsv_mask_list)
    Log_Arm1_server_print("in det color,wait 1s for next try")
    time.sleep(0.4)
    for color_name, hsv_range in zip(color_list, hsv_mask_list):
        mask_l, mask_h = hsv_range
        mask = cv2.inRange(hsv_image, mask_l, mask_h)
        mask_nonzero=np.count_nonzero(mask==255) 
        if mask_nonzero > size_threshold:
            found_color = color_name 
            found_masks[found_color] = mask  
            # Log_Arm1_server_print("size_threshold=",size_threshold)
            # Log_Arm1_server_print("{color_name}_mask_nonzero=",mask_nonzero)
            break  
    if found_color is not None:  
        Log_Arm1_server_print("in det color Found color:", found_color)      
        res = det_rect(found_masks[found_color])  
        if res :
            return mask_l,mask_h
        else:
            return None
    # else:
    #     Log_Arm1_server_print("Func->det_img:No color found")



def shift_camera_3_1():
    my_pose = pose()
    my_pose.ry = -100 / 1000
    my_pose.rx = 0
    my_pose.y = 3
    if robot_service :
        res = robot_service(my_pose,10.0,True)
        Log_Arm1_server_print("in shift_camera_2_1:res",res)
        #Log_Arm1_server_print('ok')
    else:
        exit(0)

def shift_camera_2_1():
    my_pose = pose()
    my_pose.ry = -65 / 1000
    my_pose.rx = 0
    my_pose.y = 3
    if robot_service :
        res = robot_service(my_pose,10.0,True)
        Log_Arm1_server_print("in shift_camera_2_1:res",res)
        #Log_Arm1_server_print('ok')
    else:
        exit(0)

def shift_camera_1_1():
    my_pose = pose()
    my_pose.ry = -110 / 1000
    my_pose.rx = 0
    my_pose.y = 3
    if robot_service :
        res = robot_service(my_pose,80.0,True)
        Log_Arm1_server_print("in shift_camera_1_1:res",res)
        #Log_Arm1_server_print('ok')
    else:
        exit(0)

def shift_camera_robot04():
    my_pose = pose()
    my_pose.ry = -85 / 1000
    my_pose.rx = 0
    my_pose.y = 3
    if robot_service :
        res = robot_service(my_pose,80.0,True)
        Log_Arm1_server_print("in shift_camera_robot:res",res)
        #Log_Arm1_server_print('ok')
    else:
        exit(0)

def go_back_home():
    Log_Arm1_server_print("HOME")
    run_point(-181.639,47.643,572.853,-88.358,1.226,-135.359,50.0) # 1-1���� 3-1����

def go_back_home2():
    Log_Arm1_server_print("HOME")
    run_point(-128.349,-6.319,1027.885,-88.737,1.11,-130.874,100.0) # 1-1���� 3-1����
    # run_point(1.798,-144.924,1075.885,-88.737,1.11,-134.874,50.0)##lx-2023.12.17-15.46

def send_box_example_1_1():
    Log_Arm1_server_print("send_box")
    time.sleep(1)
    run_point(96.919,46.195,677.863,-94.069,1.221,48.456,50.0)
    time.sleep(1)
    run_point(-138.629,357.543,360.198,-179.764,-0.222,45.291,50.0)
    time.sleep(1)
    # run_point(-138.629,357.543,140.000,-179.764,-0.222,45.291,10.0)
    # time.sleep(1)

def send_box_example_3_1():
    Log_Arm1_server_print("send_box")
    time.sleep(1)
    run_point(96.919,46.195,677.863,-94.069,1.221,48.456,50.0)
    time.sleep(1)
    run_point(-174.378,420.125,360.198,160.045,2.924,44.804,50.0)
    time.sleep(1)
    run_point(-174.378,420.125,140.000,160.045,2.924,44.804,10.0)
    time.sleep(1)

def send_box_release_on():
    Log_Arm1_server_print("send_realease")
    time.sleep(1)
    run_point(-153.666,362.749,360.198,-179.764,-0.222,45.291,50.0)
    time.sleep(1)

def shift_arm(pose,speed):
    if robot_service :
        res = robot_service(pose,speed,True)
        Log_Arm1_server_print('in shift_arm:res',res)
        #Log_Arm1_server_print('ok')
    else:
        exit(0)    


def run_point(x,y,z,r,p,_y_,speed,shift=False):
    point = pose()
    point.rx = x/1000
    point.ry = y/1000
    point.rz = z/1000
    point.r = r
    point.p = p
    point.y = _y_
    #Log_Arm1_server_print(robot_service)
    if robot_service:
        res = robot_service(point,speed , False)
        return res 


  


def all_init():
    global demo_lib , robot_service , ser
    try:
        # #step 1 : connect woosh robot
        # demo_lib = ctypes.CDLL('librobot_demo.so')
        # demo_lib.woosh_robot_init.argtypes = [ctypes.c_char_p]
        # #ip ��ַ��Ҫ�޸�
        # ip_addr = '192.168.1.226'
        # ip_addr = ip_addr.encode()
        # c_ip_addr = ctypes.c_char_p(ip_addr)

        # #���ӵ���
        # demo_lib.woosh_robot_init(c_ip_addr)

        #step 2 : connect grap 
        ser = serial_init()
        #wait init done.
        grap_init(ser)
        time.sleep(3)
        grap_release(ser)
        time.sleep(1)
        Log_Arm1_server_print("here1")
        #step 3 : connect camera ros
        rospy.init_node('color_box',anonymous=True)
        Log_Arm1_server_print("here2")
        rospy.wait_for_service('move_arm',timeout = 2.0)

        #step 4 : go to home point.
        service = rospy.ServiceProxy('/move_arm',robot_move)
        Log_Arm1_server_print("here3")

        robot_service = service
        if service is None:
            Log_Arm1_server_print('service error')
            exit(0)

        home_pose = pose()
        home_pose.rx = -0.318476
        home_pose.ry = 0.302017
        home_pose.rz = 0.248979
        home_pose.r = -179.613
        home_pose.p = -2.263
        home_pose.y = 44.034
        Log_Arm1_server_print('goto start point')
        #res = service(home_pose,40.0,False)
        #if not res:
        #    Log_Arm1_server_print('go home error')
        

    except:
        Log_Arm1_server_print('utils error')
        exit(0)


# if __name__ =="__main__":
#     det_color = det_color()
#     det_color()

#     pass



