import cv2
import numpy as np
import os


_detector = None
_recognizer = None

def _get_models():
    global _detector, _recognizer
    if _detector is None or _recognizer is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_dir = os.environ.get('MODEL_DIRECTORY', os.path.join(base_dir, 'models'))
        det_path = os.path.join(model_dir, 'face_detection_yunet_2023mar.onnx')
        rec_path = os.path.join(model_dir, 'face_recognition_sface_2021dec.onnx')
        
        if not os.path.exists(det_path) or not os.path.exists(rec_path):
            raise FileNotFoundError(f"Model files not found in {model_dir}. Please ensure they are deployed correctly.")
            
        _detector = cv2.FaceDetectorYN.create(det_path, "", (320, 320), score_threshold=0.6, nms_threshold=0.3, top_k=5000)
        _recognizer = cv2.FaceRecognizerSF.create(rec_path, "")
    return _detector, _recognizer

def extract_single_face_embedding(image_bytes):
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            return {"success": False, "error": "Invalid image format or corrupted file."}
            
        detector, recognizer = _get_models()
        height, width, _ = img.shape
        detector.setInputSize((width, height))
        
        faces = detector.detect(img)
        faces_data = faces[1] if faces[1] is not None else []
        
        num_faces = len(faces_data)
        
        if num_faces == 0:
            return {"success": False, "error": "No face detected. Please upload a clear photo of your face."}
        elif num_faces > 1:
            return {"success": False, "error": "Multiple faces detected. Please ensure only you are in the photo."}
            
        face = faces_data[0]
        
        aligned_face = recognizer.alignCrop(img, face)
        feature = recognizer.feature(aligned_face)
        
        if feature.shape != (1, 128):
            return {"success": False, "error": "Invalid embedding shape."}
            
        feature = feature.astype(np.float32)
        if not np.isfinite(feature).all():
            return {"success": False, "error": "Embedding contains invalid values."}
            
        return {
            "success": True, 
            "embedding": feature.tobytes(), 
            "model_name": "sface_2021dec"
        }
    except Exception as e:
        return {"success": False, "error": f"Face extraction failed: {str(e)}"}
