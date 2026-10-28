import http.client
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import realsense_camera as depth
from app import handler_type


class DepthTests(unittest.TestCase):
    def camera(self):
        camera=depth.create_camera()
        camera['token']='test-session'
        camera['last_access']=time.monotonic()
        camera['latest']=(np.zeros((480,640,3),np.uint8),np.full((480,640),750,np.float32),time.monotonic(),time.time()*1000,12,123)
        camera['ready'].set()
        return camera

    def test_median_ignores_holes_and_outliers(self):
        image=np.full((20,20),650,np.float32)
        image[7,7]=0;image[8,8]=float('nan');image[9,9]=9000
        result=depth.measure(image,10,10)
        self.assertEqual(result['mm'],650)
        self.assertEqual(result['valid_samples'],47)
        self.assertEqual(result['quantity'],'optical-axis depth Z')

    def test_missing_or_mixed_depth_is_not_presented_as_distance(self):
        self.assertIsNone(depth.measure(np.zeros((20,20)),10,10)['mm'])
        image=np.full((20,20),500.);image[:,10:]=2000
        result=depth.measure(image,10,10)
        self.assertIsNone(result['mm']);self.assertEqual(result['reason'],'MIXED_SURFACES')

    def test_pixel_validation_and_edges(self):
        image=np.full((20,20),1000.)
        for x,y in ((-1,0),(20,0),(True,2),(2.5,3),(None,3)):
            with self.subTest(x=x,y=y),self.assertRaises(ValueError):depth.measure(image,x,y)
        self.assertEqual(depth.measure(image,0,0)['mm'],1000)

    def test_color_scale_is_fixed_and_invalid_depth_is_black(self):
        first=np.array([[0,1000],[1500,3000]],np.float32)
        second=first.copy();second[1,1]=6000
        a,b=depth.colorize(first),depth.colorize(second)
        np.testing.assert_array_equal(a[0,0],[0,0,0])
        np.testing.assert_array_equal(a[0,1],b[0,1])

    def test_frame_id_age_and_session_are_required(self):
        camera=self.camera();image=np.full((240,320),500.)
        camera['frames']['now']=(image,time.monotonic())
        camera['frames']['old']=(image,time.monotonic()-3)
        self.assertEqual(depth.measure_frame(camera,'test-session','now',100,100)['range']['mm'],500)
        for token,frame in (('wrong','now'),('test-session','old'),('test-session','missing')):
            with self.assertRaises(RuntimeError):depth.measure_frame(camera,token,frame,100,100)

    def test_target_measurement_uses_the_same_resized_aligned_frame(self):
        camera=self.camera()
        camera['latest'][1][170:194,210:234]=1200
        result={'found':True,'objects':[{'label':'cup','center':[100,80],'box':[80,60,130,110],
                 'mask':{'found':True,'center':[110,90]}}], 'count':1,'backend':'test','elapsed_ms':1}
        with mock.patch('object_vision.run_vision',return_value=result):
            frame=depth.read_frame(camera,'test-session',objects={},point=[160,120])
        self.assertEqual(frame['range']['mm'],750)
        self.assertEqual(frame['result']['objects'][0]['range']['mm'],1200)
        self.assertEqual(frame['result']['objects'][0]['range']['pixel'],[110,90])
        self.assertEqual(frame['result']['frame_id'],frame['frame_id'])
        self.assertTrue(frame['rgb'].startswith('data:image/png;base64,'))
        self.assertTrue(frame['registered_to_rgb'])

    def test_stale_source_and_closed_session_cannot_produce_frames(self):
        camera=self.camera();old=list(camera['latest']);old[2]-=3;camera['latest']=tuple(old)
        with self.assertRaises(RuntimeError):depth.read_frame(camera,'test-session',detect=False)
        depth.close_camera(camera,'test-session')
        self.assertIsNone(camera['latest']);self.assertFalse(camera['frames'])
        with self.assertRaises(RuntimeError):depth.measure_frame(camera,'test-session','old',1,1)

    def test_http_origin_and_point_validation(self):
        camera=self.camera()
        class Quiet(handler_type(None,depth_camera=camera)):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def request(path,payload,origin=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            connection.request('POST',path,json.dumps(payload),headers)
            result=connection.getresponse();status=result.status;result.read();connection.close();return status
        try:
            self.assertEqual(request('/api/depth/open',{},'https://external.invalid'),403)
            self.assertEqual(request('/api/depth/frame',{'token':'test-session','point':[True,1]}),400)
            self.assertEqual(request('/api/depth/measure',{'token':'wrong','frame_id':'f','x':1,'y':1}),503)
            self.assertEqual(request('/api/depth/close',{}),400)
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)


if __name__=='__main__':unittest.main(verbosity=2)
