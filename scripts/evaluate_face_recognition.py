import os
import cv2
import numpy as np
import time
import json
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

YUNET_MODEL = os.path.join(PROJECT_ROOT, 'models', 'face_detection_yunet_2023mar.onnx')
SFACE_MODEL = os.path.join(PROJECT_ROOT, 'models', 'face_recognition_sface_2021dec.onnx')

def get_detector():
    detector = cv2.FaceDetectorYN.create(
        model=YUNET_MODEL, config='', input_size=(320, 320),
        score_threshold=0.6, nms_threshold=0.3, top_k=50
    )
    return detector

def get_recognizer():
    return cv2.FaceRecognizerSF.create(model=SFACE_MODEL, config='')

def get_embedding(img_path, detector, recognizer):
    img = cv2.imread(img_path)
    if img is None: return None, None
    height, width = img.shape[:2]
    detector.setInputSize((width, height))
    start_time = time.time()
    _, faces = detector.detect(img)
    detect_time = time.time() - start_time
    
    if faces is None or len(faces) == 0:
        return None, detect_time
        
    start_time = time.time()
    face = faces[0]
    aligned_face = recognizer.alignCrop(img, face)
    embedding = recognizer.feature(aligned_face)
    rec_time = time.time() - start_time
    
    return embedding[0], detect_time + rec_time

def evaluate():
    detector = get_detector()
    recognizer = get_recognizer()
    
    test_dir = os.path.join(PROJECT_ROOT, 'tests', 'face_test_data')
    students = ['student_1', 'student_2']
    
    embeddings = {}
    metrics = {
        'total_images': 0,
        'detected_faces': 0,
        'zero_detections': 0,
        'true_matches': [],
        'non_matches': [],
        'total_time': 0,
        'classroom_stats': {}
    }
    
    # 1. Enroll first image
    for s in students:
        s_dir = os.path.join(test_dir, s)
        if not os.path.exists(s_dir): continue
        files = [f for f in os.listdir(s_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
        if files:
            emb, t = get_embedding(os.path.join(s_dir, files[0]), detector, recognizer)
            if emb is not None:
                embeddings[s] = emb
                
    # 2. Test matches
    for s in students:
        s_dir = os.path.join(test_dir, s)
        if not os.path.exists(s_dir): continue
        files = [f for f in os.listdir(s_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
        for f in files[1:]: # Skip enrollment image
            emb, t = get_embedding(os.path.join(s_dir, f), detector, recognizer)
            metrics['total_images'] += 1
            if emb is None:
                metrics['zero_detections'] += 1
                continue
            metrics['detected_faces'] += 1
            
            # Compare with everyone
            for enrolled_s, enrolled_emb in embeddings.items():
                sim = recognizer.match(enrolled_emb, emb, cv2.FaceRecognizerSF_FR_COSINE)
                if enrolled_s == s:
                    metrics['true_matches'].append(float(sim))
                else:
                    metrics['non_matches'].append(float(sim))

    # 3. Classroom
    class_dir = os.path.join(test_dir, 'classroom')
    if os.path.exists(class_dir):
        files = [f for f in os.listdir(class_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
        if files:
            img_path = os.path.join(class_dir, files[0])
            img = cv2.imread(img_path)
            if img is not None:
                h, w = img.shape[:2]
                detector.setInputSize((w, h))
                start_time = time.time()
                _, faces = detector.detect(img)
                detect_time = time.time() - start_time
                
                metrics['classroom_stats']['dimensions'] = f"{w}x{h}"
                metrics['classroom_stats']['detection_time'] = detect_time
                
                rec_start = time.time()
                faces_count = 0
                if faces is not None:
                    faces_count = len(faces)
                    for face in faces:
                        aligned = recognizer.alignCrop(img, face)
                        recognizer.feature(aligned)
                rec_time = time.time() - rec_start
                
                metrics['classroom_stats']['faces_detected'] = faces_count
                metrics['classroom_stats']['recognition_time'] = rec_time
                metrics['classroom_stats']['total_time'] = detect_time + rec_time

    # 4. Threshold analysis
    candidates = [0.25, 0.30, 0.363, 0.40, 0.45, 0.50]
    analysis = []
    
    true_labels = [1]*len(metrics['true_matches']) + [0]*len(metrics['non_matches'])
    scores = metrics['true_matches'] + metrics['non_matches']
    
    for thr in candidates:
        tp = sum(1 for s in metrics['true_matches'] if s >= thr)
        fn = sum(1 for s in metrics['true_matches'] if s < thr)
        fp = sum(1 for s in metrics['non_matches'] if s >= thr)
        tn = sum(1 for s in metrics['non_matches'] if s < thr)
        
        precision = tp / (tp + fp) if (tp+fp) > 0 else 0
        recall = tp / (tp + fn) if (tp+fn) > 0 else 0
        far = fp / (fp + tn) if (fp+tn) > 0 else 0
        frr = fn / (tp + fn) if (tp+fn) > 0 else 0
        
        analysis.append({
            'threshold': thr,
            'TP': tp, 'FN': fn, 'FP': fp, 'TN': tn,
            'Precision': round(precision, 4),
            'Recall': round(recall, 4),
            'FAR': round(far, 4),
            'FRR': round(frr, 4)
        })

    metrics['candidate_analysis'] = analysis
    
    report_path = os.path.join(PROJECT_ROOT, 'evaluation_report.json')
    with open(report_path, 'w') as f:
        json.dump(metrics, f, indent=4)
        
    print(json.dumps(metrics, indent=4))

if __name__ == '__main__':
    evaluate()
