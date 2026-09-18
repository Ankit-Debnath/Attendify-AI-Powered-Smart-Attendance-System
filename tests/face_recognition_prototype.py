import cv2
import numpy as np
import os
import glob

def init_models():
    detector = cv2.FaceDetectorYN.create(
        "models/face_detection_yunet_2023mar.onnx",
        "",
        (320, 320),
        score_threshold=0.6,
        nms_threshold=0.3,
        top_k=5000
    )
    recognizer = cv2.FaceRecognizerSF.create(
        "models/face_recognition_sface_2021dec.onnx",
        ""
    )
    return detector, recognizer

def process_student_images(detector, recognizer, base_dir):
    students = ['student_1', 'student_2', 'student_3']
    
    student_embeddings = {}
    stats = {
        'student_1_imgs': 0,
        'student_2_imgs': 0,
        'student_3_imgs': 0,
        'valid_embeddings': 0,
        'invalid_images': 0
    }
    
    for s_dir in students:
        s_path = os.path.join(base_dir, s_dir)
        student_embeddings[s_dir] = []
        
        if not os.path.exists(s_path):
            continue
            
        images = glob.glob(os.path.join(s_path, "*.*"))
        stats[f'{s_dir}_imgs'] = len(images)
        
        for img_path in images:
            img = cv2.imread(img_path)
            if img is None:
                print(f"[{s_dir}] Failed to load image: {os.path.basename(img_path)}")
                stats['invalid_images'] += 1
                continue
                
            height, width, _ = img.shape
            detector.setInputSize((width, height))
            faces = detector.detect(img)
            faces_data = faces[1] if faces[1] is not None else []
            
            if len(faces_data) == 0:
                print(f"[{s_dir}] ZERO faces detected in {os.path.basename(img_path)}. Skipping.")
                stats['invalid_images'] += 1
                continue
            elif len(faces_data) > 1:
                print(f"[{s_dir}] MULTIPLE faces ({len(faces_data)}) detected in {os.path.basename(img_path)}. Invalid for enrollment. Skipping.")
                stats['invalid_images'] += 1
                continue
                
            # Exactly one face
            face = faces_data[0]
            try:
                aligned_face = recognizer.alignCrop(img, face)
                feature = recognizer.feature(aligned_face)
                
                student_embeddings[s_dir].append({
                    "path": img_path,
                    "feature": feature,
                    "shape": feature.shape,
                    "dtype": feature.dtype
                })
                stats['valid_embeddings'] += 1
                
                print(f"[{s_dir}] Extracted embedding for {os.path.basename(img_path)}")
                print(f"  Shape: {feature.shape} | Dtype: {feature.dtype}")
                
            except Exception as e:
                print(f"[{s_dir}] Feature extraction failed for {os.path.basename(img_path)}: {e}")
                stats['invalid_images'] += 1
                
    return student_embeddings, stats

def calculate_similarities(recognizer, student_embeddings):
    same_person_sims = []
    diff_person_sims = []
    
    students = list(student_embeddings.keys())
    
    print("\n--- SAME-PERSON COMPARISONS ---")
    for s_dir, embeddings in student_embeddings.items():
        n = len(embeddings)
        for i in range(n):
            for j in range(i+1, n):
                sim = recognizer.match(embeddings[i]['feature'], embeddings[j]['feature'], cv2.FaceRecognizerSF_FR_COSINE)
                same_person_sims.append(sim)
                print(f"Pair: {os.path.basename(embeddings[i]['path'])} & {os.path.basename(embeddings[j]['path'])}")
                print(f"Same/Different: SAME")
                print(f"Cosine Similarity: {sim:.4f}")
                print(f"Detection: Success | Shape: {embeddings[i]['shape']} | Dtype: {embeddings[i]['dtype']}\n")
                
    print("\n--- DIFFERENT-PERSON COMPARISONS ---")
    for i in range(len(students)):
        for j in range(i+1, len(students)):
            emb_i = student_embeddings[students[i]]
            emb_j = student_embeddings[students[j]]
            
            for f_i in emb_i:
                for f_j in emb_j:
                    sim = recognizer.match(f_i['feature'], f_j['feature'], cv2.FaceRecognizerSF_FR_COSINE)
                    diff_person_sims.append(sim)
                    print(f"Pair: {os.path.basename(f_i['path'])} & {os.path.basename(f_j['path'])}")
                    print(f"Same/Different: DIFFERENT")
                    print(f"Cosine Similarity: {sim:.4f}")
                    print(f"Detection: Success | Shape: {f_i['shape']} | Dtype: {f_i['dtype']}\n")
                    
    return same_person_sims, diff_person_sims

def process_classroom_images(detector, recognizer, base_dir):
    classroom_dir = os.path.join(base_dir, 'classroom')
    stats = {'faces_detected': 0, 'embeddings_extracted': 0}
    
    if not os.path.exists(classroom_dir):
        return stats
        
    images = glob.glob(os.path.join(classroom_dir, "*.*"))
    print("\n--- CLASSROOM RESULTS ---")
    
    for img_path in images:
        print(f"\nProcessing Classroom Image: {os.path.basename(img_path)}")
        img = cv2.imread(img_path)
        if img is None:
            print("Failed to load image.")
            continue
            
        height, width, _ = img.shape
        detector.setInputSize((width, height))
        faces = detector.detect(img)
        faces_data = faces[1] if faces[1] is not None else []
        
        print(f"Faces Detected: {len(faces_data)}")
        stats['faces_detected'] += len(faces_data)
        
        for idx, face in enumerate(faces_data):
            conf = face[-1]
            try:
                aligned_face = recognizer.alignCrop(img, face)
                feature = recognizer.feature(aligned_face)
                stats['embeddings_extracted'] += 1
                
                print(f"  Face {idx+1}: Confidence={conf:.4f} | Emb Shape={feature.shape} | Emb Dtype={feature.dtype}")
            except Exception as e:
                print(f"  Face {idx+1}: Confidence={conf:.4f} | Embedding extraction failed: {e}")
                
    return stats

def main():
    print("Initializing models...")
    try:
        detector, recognizer = init_models()
    except Exception as e:
        print(f"Failed to initialize models: {e}")
        return
        
    base_dir = "tests/face_test_data"
    
    print("\nProcessing Student Images...")
    student_embeddings, student_stats = process_student_images(detector, recognizer, base_dir)
    
    same_sims, diff_sims = calculate_similarities(recognizer, student_embeddings)
    
    class_stats = process_classroom_images(detector, recognizer, base_dir)
    
    def safe_min(arr): return min(arr) if arr else 'N/A'
    def safe_max(arr): return max(arr) if arr else 'N/A'
    def safe_mean(arr): return sum(arr)/len(arr) if arr else 'N/A'
    
    print("\nDATASET SUMMARY")
    print("---------------")
    print(f"Student 1 images: {student_stats['student_1_imgs']}")
    print(f"Student 2 images: {student_stats['student_2_imgs']}")
    print(f"Student 3 images: {student_stats['student_3_imgs']}")
    print("")
    print(f"Valid embeddings: {student_stats['valid_embeddings']}")
    print(f"Invalid images: {student_stats['invalid_images']}")
    print("")
    print("SAME-PERSON SIMILARITIES:")
    print(f"min: {safe_min(same_sims):.4f}" if same_sims else "min: N/A")
    print(f"max: {safe_max(same_sims):.4f}" if same_sims else "max: N/A")
    print(f"mean: {safe_mean(same_sims):.4f}" if same_sims else "mean: N/A")
    print("")
    print("DIFFERENT-PERSON SIMILARITIES:")
    print(f"min: {safe_min(diff_sims):.4f}" if diff_sims else "min: N/A")
    print(f"max: {safe_max(diff_sims):.4f}" if diff_sims else "max: N/A")
    print(f"mean: {safe_mean(diff_sims):.4f}" if diff_sims else "mean: N/A")
    print("")
    print("CLASSROOM:")
    print(f"faces detected: {class_stats['faces_detected']}")
    print(f"embeddings extracted: {class_stats['embeddings_extracted']}")
    print("")
    print("THRESHOLD:")
    print("NOT SELECTED")

if __name__ == '__main__':
    main()
