import cv2

VIDEO = "./source/VV.mp4"

cap = cv2.VideoCapture(VIDEO)

if not cap.isOpened():
    print("비디오를 열 수 없습니다.")
    exit()

total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
current_frame = 0

# 창 생성 및 전체화면 설정
win_name = "Frame-by-Frame Analyzer"
cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

print("※ Shortcut Keys:")
print("  - [Q] / [W] : Move 1 frame (Backward / Forward)")
print("  - [A] / [S] : Move 50 frames (Backward / Forward)")
print("  - [Z] / [X] : Move 200 frames (Backward / Forward)")
print("  - [F] : Toggle Fullscreen")
print("  - [ESC] : Exit")
fullscreen_mode = True

while True:
    cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
    ret, frame = cap.read()
    
    if not ret:
        current_frame = max(0, current_frame - 1)
        continue

    display_frame = frame.copy()
    cv2.putText(display_frame, f"Frame: {current_frame}/{total_frames}", (50, 80), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3, cv2.LINE_AA)
    
    cv2.imshow(win_name, display_frame)
    
    # 32비트 원본 키코드와, 하위 8비트만 마스킹한 키코드를 모두 가져옵니다.
    raw_key = cv2.waitKeyEx(0)
    key_8bit = raw_key & 0xFF
    
    # [Q] / [W] Move 1 frame
    if key_8bit == ord('q') or key_8bit == ord('Q'):
        if current_frame > 0:
            current_frame -= 1
    elif key_8bit == ord('w') or key_8bit == ord('W'):
        if current_frame < total_frames - 1:
            current_frame += 1
            
    # [A] / [S] Move 50 frames
    elif key_8bit == ord('a') or key_8bit == ord('A'):
        current_frame = max(0, current_frame - 50)
    elif key_8bit == ord('s') or key_8bit == ord('S'):
        current_frame = min(total_frames - 1, current_frame + 50)

    # [Z] / [X] Move 200 frames
    elif key_8bit == ord('z') or key_8bit == ord('Z'):
        current_frame = max(0, current_frame - 200)
    elif key_8bit == ord('x') or key_8bit == ord('X'):
        current_frame = min(total_frames - 1, current_frame + 200)
    # [F] 전체화면 토글
    elif key_8bit == ord('f') or key_8bit == ord('F'):
        fullscreen_mode = not fullscreen_mode
        if fullscreen_mode:
            cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            
    # [ESC] Exit
    elif key_8bit == 27:
        break

cap.release()
cv2.destroyAllWindows()