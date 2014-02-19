#!/usr/bin/env python  
import roslib
roslib.load_manifest('camera_robot_calibration')
import rospy
import tf
import PyKDL
import numpy as num
from std_msgs.msg import String
from geometry_msgs.msg import Pose, Point, Quaternion
from tf_conversions import posemath



from std_srvs.srv import Empty, EmptyResponse

from camera_robot_calibration_module import camera_robot_calibration

def safe_pose_to_file(f,P):
    f.write(str(P.position.x)+'\t')
    f.write(str(P.position.y)+'\t')
    f.write(str(P.position.z)+'\t')
    f.write(str(P.orientation.x)+'\t')
    f.write(str(P.orientation.y)+'\t')
    f.write(str(P.orientation.z)+'\t')
    f.write(str(P.orientation.w)+'\n')
    f.flush()


class camera_robot_calibration_ros():
    def __init__(self):
        #read values from properties
        self.base_frame_name=rospy.get_param('base_frame_name', '/base_link')
        self.camera_frame_name=rospy.get_param('camera_frame_name', '/camera_link')
        self.robot_ee_frame_name=rospy.get_param('robot_ee_frame_name', '/lwr_arm_link_7')
        self.target_frame_name=rospy.get_param('target_frame_name', '/marker_frame')
        #self.save=rospy.get_param('auto_save_to_file', True)
        
        #nominal positions of camera w.r.t world and marker mounted in the robot
        #this two frames are published
        unity_frame=Pose()
        unity_frame.orientation.w=1; 
        unity_frame.position.z=0.1; 
        # marker in ee
        self.ee_P_m=rospy.get_param('robot_ee_pose_camera', unity_frame);
        # camera base in world
        
        init_camera_pose=PyKDL.Frame(PyKDL.Rotation.RPY(0,0,1.57*3/2+0.8),
                PyKDL.Vector(-2,0,0.5))
        
        self.w_P_c=rospy.get_param('nominal_pose_camera', posemath.toMsg(init_camera_pose));
        
        #setup TF LISTENER AND BROADCASTER
        self.br = tf.TransformBroadcaster()
        self.listener = tf.TransformListener()
        
        #vectors of saved data
        self.crc=camera_robot_calibration()
        
        #create services
        self.s1 = rospy.Service('read_tfs', Empty, self.read_tfs)
        self.s2 = rospy.Service('compute_frames', Empty, self.compute_frames)
        self.s3 = rospy.Service('reset_frames', Empty, self.reset_frames)
        #save to file
        self.f= open('data.txt', 'w')
        #save initial positions
        safe_pose_to_file(self.f,self.w_P_c)
        safe_pose_to_file(self.f,self.ee_P_m)
        
    def reset_frames(self,req): 
        """empty vectors to reset algorithm"""  
        self.crc.reset_frames()
        return EmptyResponse()
        
    def current_pose(self, frame_source, frame_target):
        if self.listener == None:
            rospy.loginfo("No transform listener available. Constructing new one.")
            self.listener = tf.TransformListener()

        try:
            now = rospy.Time(0)
            self.listener.waitForTransform(frame_source, frame_target, now, rospy.Duration(0.3))
            (trans, rot) = self.listener.lookupTransform(frame_source, frame_target, now)

            pose = Pose()
            pose.position.x = trans[0]
            pose.position.y = trans[1]
            pose.position.z = trans[2]
            pose.orientation.x = rot[0]
            pose.orientation.y = rot[1]
            pose.orientation.z = rot[2]
            pose.orientation.w = rot[3]           
            return pose
        except (tf.LookupException, tf.ConnectivityException):
            print "Service call failed: %s" % e
            return 0
        
        
        
        
    def compute_frames(self,req):
            #read nominal poses, and set as initial positions
    
            self.crc.set_intial_frames(posemath.fromMsg( self.w_P_c),
                                        posemath.fromMsg(self.ee_P_m))

            
            #do several iteration of estimation

            n_comp=6
            residue_max=[]
            residue_mod=[]
            for i in range(n_comp):
                print '\ncurrent position'
                print self.crc.w_T_c.p
                residue= self.crc.compute_frames();
                r2=residue.transpose()*residue
                residue_mod.append( num.sqrt (r2[0,0]))
                residue_max.append(num.max(residue))
            print '\nresidue_mod'
            print residue_mod
            print '\nresidue_max'
            print residue_max
            #put result back in parameter
            print '\nee_T_m'
            print self.crc.ee_T_m
            print '\nw_T_c'
            print self.crc.w_T_c
            self.ee_P_m = posemath.toMsg(self.crc.ee_T_m)
            self.w_P_c=posemath.toMsg(self.crc.w_T_c)
            
            return EmptyResponse();
        
    def read_tfs(self,req):
        #marker w.r.t. camera\print
      
        ok=True

        #read target w.r.t. camera
        c_P_m=self.current_pose(self.camera_frame_name,self.target_frame_name)
        if(c_P_m==0):
            ok=False
        w_P_ee=self.current_pose(self.base_frame_name,self.robot_ee_frame_name)
        if(w_P_ee==0):
            ok=False
        #ee w.r.t. base
      
     
        if ok:
            print "stored robot position:"
            print w_P_ee
            print "stored marker position:"
            print c_P_m
            #save data
            safe_pose_to_file(self.f,w_P_ee)
            safe_pose_to_file(self.f,c_P_m)
            self.crc.store_frames(posemath.fromMsg( w_P_ee),posemath.fromMsg(c_P_m))
        else:
            print "error in retrieving a frame"
            
        return EmptyResponse();


    def publish_tfs(self):
        #publish the estimated poses of marker and camera, in tf
       
        self.br.sendTransform((self.w_P_c.position.x,self.w_P_c.position.y,self.w_P_c.position.z),  
                         (self.w_P_c.orientation.w,self.w_P_c.orientation.x,self.w_P_c.orientation.y,self.w_P_c.orientation.z),
                         rospy.Time.now(),
                         self.camera_frame_name,
                         self.base_frame_name)
        
        self.br.sendTransform((self.ee_P_m.position.x,self.ee_P_m.position.y,self.ee_P_m.position.z),  
                         (self.ee_P_m.orientation.w,self.ee_P_m.orientation.x,self.ee_P_m.orientation.y,self.ee_P_m.orientation.z),
                         rospy.Time.now(),
                         self.target_frame_name+"_nominal",
                         self.robot_ee_frame_name)
    
        

                
            
            #

if __name__ == '__main__':
    print "init"
    rospy.init_node('camera_robot_calibration')
    est=camera_robot_calibration_ros()
    
    while not rospy.is_shutdown():
      est.publish_tfs()
      rospy.sleep(0.01)

    rospy.spin()
