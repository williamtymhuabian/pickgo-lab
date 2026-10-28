"""Explicit, in-memory RGB-D acquisition and axial depth measurement for RealSense."""
import base64
import importlib.util
from pathlib import Path
import secrets
import sys
import threading
import time

RUNTIME = Path(__file__).resolve().parent / '.runtime/realsense'
MAX_FRAME_AGE = 2.5
IDLE_SECONDS = 10


def sdk_present():
    return importlib.util.find_spec('pyrealsense2') is not None or (RUNTIME/'pyrealsense2').is_dir()


def load_sdk():
    if RUNTIME.is_dir() and str(RUNTIME) not in sys.path:
        sys.path.insert(0, str(RUNTIME))
    try:
        import pyrealsense2 as rs
        return rs
    except ImportError as error:
        raise RuntimeError('未找到 RealSense SDK；RGB 模式仍可使用，请准备 requirements-depth.txt 中的可选运行库') from error


def measure(depth_mm, x, y, radius=3):
    import numpy as np
    h, w = depth_mm.shape
    if type(x) is not int or type(y) is not int or not (0 <= x < w and 0 <= y < h):
        raise ValueError('测距像素必须位于当前图像内')
    roi = depth_mm[max(0,y-radius):min(h,y+radius+1), max(0,x-radius):min(w,x+radius+1)]
    valid = roi[np.isfinite(roi) & (roi >= 150) & (roi <= 10000)]
    result = {'pixel': [x,y], 'mm': None, 'valid_samples': int(valid.size),
              'total_samples': int(roi.size), 'method': 'aligned 7x7 median', 'quantity': 'optical-axis depth Z'}
    if valid.size < 9 or valid.size/roi.size < .3:
        return {**result, 'reason': 'NO_VALID_DEPTH'}
    median = float(np.median(valid))
    spread = float(np.percentile(valid,90)-np.percentile(valid,10))
    if spread > max(60, median*.12):
        return {**result, 'reason': 'MIXED_SURFACES', 'spread_mm': round(spread,1)}
    return {**result, 'mm': round(median,1), 'spread_mm': round(spread,1), 'reason': None}


def colorize(depth_mm):
    import cv2
    import numpy as np
    # A fixed scale makes the same distance keep the same colour across frames.
    shade = np.clip((3000-depth_mm)/(3000-200)*255,0,255).astype(np.uint8)
    image = cv2.applyColorMap(shade,cv2.COLORMAP_TURBO)
    image[(~np.isfinite(depth_mm)) | (depth_mm <= 0)] = 0
    return image


def png(image):
    import cv2
    ok, data = cv2.imencode('.png',image)
    if not ok:
        raise RuntimeError('无法编码 RGB-D 预览')
    return 'data:image/png;base64,'+base64.b64encode(data).decode('ascii')


def create_camera(factory=load_sdk):
    return {'lock':threading.RLock(), 'factory':factory, 'pipeline':None, 'token':None,
            'thread':None, 'stop':None, 'ready':threading.Event(), 'latest':None,
            'last_access':0, 'error':None, 'frames':{}, 'sequence':0, 'name':None}


def status(camera):
    with camera['lock']:
        return {'backend':'realsense', 'sdk_available':sdk_present(), 'opened':camera['token'] is not None,
                'device':camera['name'], 'registered_to_rgb':camera['token'] is not None,
                'storage':'memory only', 'idle_timeout_s':IDLE_SECONDS}


def require_token(camera, token):
    if not isinstance(token,str) or not camera['token'] or not secrets.compare_digest(camera['token'],token):
        raise RuntimeError('RGB-D 会话已关闭或被替换，请重新打开')


def close_camera(camera, token=None):
    with camera['lock']:
        if token is not None:
            require_token(camera,token)
        pipe,worker,stop = camera['pipeline'],camera['thread'],camera['stop']
        camera.update(pipeline=None,token=None,latest=None,thread=None,frames={},name=None)
        camera['ready'].set()
        if stop:
            stop.set()
    if pipe:
        try:
            pipe.stop()
        except RuntimeError:
            pass
    if worker and worker is not threading.current_thread():
        worker.join(timeout=2)
    return {'opened':False}


def acquire(camera, rs, pipe, align, scale, token, stop):
    import numpy as np
    while not stop.is_set():
        with camera['lock']:
            if camera['token'] != token:
                return
            expired = time.monotonic()-camera['last_access'] > IDLE_SECONDS
        if expired:
            close_camera(camera,token)
            return
        try:
            frames = align.process(pipe.wait_for_frames(1200))
            depth,color = frames.get_depth_frame(),frames.get_color_frame()
            if not depth or not color:
                continue
            # Never associate unrelated browser RGB with SDK depth.
            delta = abs(depth.get_timestamp()-color.get_timestamp())
            if delta > 100:
                continue
            snapshot = (np.asanyarray(color.get_data()).copy(),
                        np.asanyarray(depth.get_data()).astype(np.float32)*scale*1000,
                        time.monotonic(),time.time()*1000,delta,int(depth.get_frame_number()))
            with camera['lock']:
                if camera['token'] != token:
                    return
                camera['latest'] = snapshot
                camera['error'] = None
                camera['ready'].set()
        except RuntimeError:
            with camera['lock']:
                if camera['token'] != token:
                    return
                camera['error'] = '未收到有效 RGB-D 帧，请检查 USB 连接或设备占用'
                camera['ready'].set()


def open_camera(camera):
    with camera['lock']:
        if camera['token']:
            raise RuntimeError('RGB-D 已被一个页面打开，请先在原页面关闭或等待空闲释放')
        rs = camera['factory']()
        devices = list(rs.context().query_devices())
        if not devices:
            raise RuntimeError('没有找到 RealSense，请检查 USB 连接')
        candidates = [d for d in devices if 'D435' in d.get_info(rs.camera_info.name)]
        if len(candidates) != 1:
            raise RuntimeError('需要恰好一台 D435；多台设备需显式选择，当前不自动猜测')
        device = candidates[0]
        config = rs.config()
        config.enable_device(device.get_info(rs.camera_info.serial_number))
        config.enable_stream(rs.stream.depth,640,480,rs.format.z16,30)
        config.enable_stream(rs.stream.color,640,480,rs.format.bgr8,30)
        pipe = rs.pipeline()
        try:
            profile = pipe.start(config)
            scale = profile.get_device().first_depth_sensor().get_depth_scale()
            align = rs.align(rs.stream.color)
        except RuntimeError as error:
            try:
                pipe.stop()
            except RuntimeError:
                pass
            raise RuntimeError('无法打开 D435，请先关闭浏览器 RGB 预览或其他相机程序') from error
        token,stop = secrets.token_urlsafe(24),threading.Event()
        camera['ready'].clear()
        camera.update(pipeline=pipe,token=token,stop=stop,latest=None,error=None,frames={},
                      last_access=time.monotonic(),name=device.get_info(rs.camera_info.name))
        worker = threading.Thread(target=acquire,args=(camera,rs,pipe,align,scale,token,stop),daemon=True)
        camera['thread'] = worker
        worker.start()
        return {**status(camera),'token':token}


def read_frame(camera, token, objects=None, detect=True, point=None, task='objects', confidence_pct=40, classes=None):
    import cv2
    with camera['lock']:
        require_token(camera,token)
        camera['last_access'] = time.monotonic()
    camera['ready'].wait(4)
    with camera['lock']:
        require_token(camera,token)
        snapshot = camera['latest']
        if snapshot is None or time.monotonic()-snapshot[2] > 1.5:
            raise RuntimeError(camera['error'] or 'RGB-D 正在启动或观测已过期，请重新采集')
        camera['sequence'] += 1
        frame_id = 'rgbd-'+str(camera['sequence'])
    color,depth,captured,epoch,delta,sdk_frame = snapshot
    # Both images use the same resize transform after SDK depth-to-colour alignment.
    rgb = cv2.resize(color,(320,240),interpolation=cv2.INTER_AREA)
    mm = cv2.resize(depth,(320,240),interpolation=cv2.INTER_NEAREST)
    result = {'found':False,'objects':[]}
    if detect and objects is not None:
        from object_vision import run_vision
        if task not in ('objects','segment'):
            raise ValueError('RGB-D 当前支持物体检测或检测加前景分割')
        result = run_vision(objects,rgb,task,confidence_pct,classes or [],max_objects=5)
    for item in result['objects']:
        mask = item.get('mask')
        center = mask['center'] if mask and mask.get('found') else item['center']
        x,y = [int(round(v)) for v in center]
        item['range'] = measure(mm,min(319,max(0,x)),min(239,max(0,y)))
    x,y = point if point is not None else (160,120)
    distance = measure(mm,x,y)
    with camera['lock']:
        require_token(camera,token)
        if time.monotonic()-captured > MAX_FRAME_AGE:
            raise RuntimeError('RGB-D 帧处理后已过期，请重新采集')
        camera['frames'] = {key:value for key,value in camera['frames'].items() if time.monotonic()-value[1] <= MAX_FRAME_AGE}
        camera['frames'][frame_id] = (mm,captured)
        while len(camera['frames']) > 8:
            del camera['frames'][next(iter(camera['frames']))]
    return {'frame_id':frame_id,'sdk_frame':sdk_frame,'timestamp_ms':epoch,'age_ms':round((time.monotonic()-captured)*1000),
            'source_size':[640,480],'image_size':[320,240],'registered_to_rgb':True,'rgb':png(rgb),
            'depth_preview':png(colorize(mm)),'color_scale_mm':[200,3000], 'range':distance,
            'result':{**result,'frame_id':frame_id,'image_size':[320,240]},
            'sync_delta_ms':round(delta,2),'valid_ratio':round(float((mm>0).mean()),3)}


def measure_frame(camera, token, frame_id, x, y):
    with camera['lock']:
        require_token(camera,token)
        value = camera['frames'].get(frame_id)
        if value is None or time.monotonic()-value[1] > MAX_FRAME_AGE:
            raise RuntimeError('所选 RGB-D 帧已过期，请先重新采集')
        return {'frame_id':frame_id,'range':measure(value[0],x,y)}
