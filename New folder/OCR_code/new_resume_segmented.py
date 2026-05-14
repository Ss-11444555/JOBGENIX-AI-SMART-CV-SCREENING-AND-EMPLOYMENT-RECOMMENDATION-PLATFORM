import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
import layoutparser as lp
import matplotlib.pyplot as plt
from ultralytics import YOLO
from collections import defaultdict, Counter
from ollama_test import extract_data_with_ollama, generate_extraction_prompt
from pdf2image import convert_from_path
from pathlib import Path
import json
import pytesseract


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- CONFIGURATION CONSTANTS ---
DEFAULT_KERNEL_WIDTH = 20
SINGLE_COLUMN_RATIO_THRESHOLD = 1.5
COLUMN_SPLIT_THRESHOLD_X = 50
LINE_X_OFFSET = 0

MIN_NOISE_AREA = 1
MIN_HEIGHT_THRESHOLD = 5

WIDTH_RATIO_THRESHOLD = 2 / 3
MAX_HEADING_COUNT = 7 
BOX_THICKNESS = 2

HORIZONTAL_LINK_COLOR = (255, 0, 255) # Magenta in BGR
HORIZONTAL_LINK_THICKNESS = 1

# Colors (BGR)
H1_COLOR = (0, 0, 255)
H2_COLOR = (0, 128, 255)
H3_COLOR = (0, 255, 255)
TEXT_COLOR = (0, 255, 0)
NARROW_SECTION_LINE_COLOR = (255, 0, 0)
NARROW_SECTION_LINE_THICKNESS = 5


HEADING_RANK = {'H1': 1, 'H2': 2, 'H3': 3, 'TEXT': 4}

# MODEL_DIR = "D:/LayoutParser/models"
# pytesseract.pytesseract.tesseract_cmd = r"E:\Tesseract\tesseract.exe" # <-- UNCOMMENT AND SET THIS PATH!

PYTESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe" 
pytesseract.pytesseract.tesseract_cmd = PYTESSERACT_CMD

#POPPLER_PATH = r"D:\Sem5\WORKSHOP2_V2_Farouk\OCR_code\poppler-25.11.0\Library\bin"
POPPLER_PATH = r"D:\Sem5\WORKSHOP2_V2_Farouk\OCR_code\poppler-25.11.0\Library\bin"


YOLO_MODEL_PATH = "yolov12l-doclaynet.pt"
HEADER_CLASSES = ["Section-header", "Title"]
YOLO_CONF_THRESHOLD = 0.25 

#----------------- Convert from PDF to Image (Helper for Main) -------------------
def convert_pdf_to_image(pdf_file_path: str, output_image_path: str):
    """
    Converts the first page of a PDF to a PNG image file.
    Returns the path to the saved image file on success, or None on failure.
    """
    print(f"Converting first page of {pdf_file_path} to image...")
    try:
        # We pass the Poppler path directly to the conversion function
        images = convert_from_path(
            pdf_file_path,
            dpi=300,  # High DPI is better for OCR accuracy
            poppler_path=POPPLER_PATH
        )
        
        if images:
            images[0].save(output_image_path, 'PNG')
            return output_image_path
        else:
            print(" PDF conversion failed: No pages found.")
            return None

    except Exception as e:
        print(f" PDF conversion failed. Is Poppler installed and POPPLER_PATH correct? Error: {e}")
        return None
    

# ---------------- YOLO HEADER DETECTION ----------------
def detect_yolo_headers(image_path, model_path=YOLO_MODEL_PATH, conf_thresh=YOLO_CONF_THRESHOLD, device='cuda'):
    """
    Run YOLO model on image and return headers as a list of dicts. (Code omitted for brevity)
    """
    try:
        if not os.path.exists(model_path):
            print(f"YOLO model not found at {model_path}; skipping header detection.")
            return []
        image = cv2.imread(image_path)
        if image is None:
            print(f"Failed to read image at {image_path} for YOLO detection.")
            return []

        model = YOLO(model_path)
        
        h, w = image.shape[:2]
        
        if h < 1024 or w < 1024:
            IMAGE_SIZE = 1024
        else:
            IMAGE_SIZE = h if h > w else w

        results = model.predict(image, device=device, conf=conf_thresh, imgsz=1000)

        header_blocks = []
        for res in results:
            names = res.names
            for b in res.boxes:
                cls_idx = int(b.cls[0])
                name = names.get(cls_idx, "")
                if name not in HEADER_CLASSES:
                    continue

                xyxy = b.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = map(int, xyxy[:4])
                score = float(b.conf[0])

                if name == "Title":
                    label = "H1"
                elif name == "Section-header":
                    label = "H2"

                header_blocks.append({
                    "label": label,
                    "height": int(y2 - y1),
                    "coords": (y1, y2, x1, x2),
                    "score": score,
                    "source": "yolo"
                })
        return header_blocks

    except Exception as e:
        print("YOLO header detection failed:", e)
        return []

# ---------------- VISUALIZATION HELPERS ----------------
def yolo_headers_to_layout(yolo_headers):
    blocks = []
    for h in yolo_headers:
        y1, y2, x1, x2 = h['coords']
        rect = lp.Rectangle(x1, y1, x2, y2)
        blocks.append(lp.TextBlock(rect, type=h['label'], score=h.get('score', 1.0)))
    return lp.Layout(blocks)

def visualize_layout(image_path, layout, color_map=None):
    image = cv2.imread(image_path)
    if image is None: return None
    drawn = image.copy()
    for block in layout:
        x1, y1, x2, y2 = map(int, [block.block.x_1, block.block.y_1, block.block.x_2, block.block.y_2])
        color = color_map.get(block.type, (0, 255, 0)) if color_map else (0, 255, 0)
        cv2.rectangle(drawn, (x1, y1), (x2, y2), color, 2)
        text_label = str(block.type) if block.type else "Text"
        cv2.putText(drawn, text_label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return drawn

def display_workflow_interactive(composite_image, title):
    if composite_image is None: return
    rgb_composite = cv2.cvtColor(composite_image, cv2.COLOR_BGR2RGB)
    plt.figure(figsize=(15, 15))
    plt.imshow(rgb_composite)
    plt.title(title)
    plt.axis('off')
    plt.show()

def plot_height_distribution(all_heights):
    # Code omitted for brevity
    pass

def create_coord_to_label_map(all_classified_sections):
    coord_map = {}
    for item in all_classified_sections:
        if 'coords' in item and 'label' in item:
            coord_map[item['coords']] = item['label']
    return coord_map

# ---------------- COLUMN SEGMENTATION (dynamic split) ----------------
def segment_into_columns(classified_sections):
    # Code omitted for brevity
    if not classified_sections: return classified_sections, []
    # ... (column segmentation logic) ...
    x_split = None
    significant_headings = [item for item in classified_sections if item['label'] in ['H1', 'H2']]

    for i in range(len(significant_headings)):
        h1 = significant_headings[i]
        for j in range(i + 1, len(significant_headings)):
            h2 = significant_headings[j]
            h1_rank = HEADING_RANK.get(h1['label'], 4)
            h2_rank = HEADING_RANK.get(h2['label'], 4)
            if h1_rank != h2_rank: continue

            h1_y1, h1_y2, h1_x1, h1_x2 = h1['coords']
            h2_y1, h2_y2, h2_x1, h2_x2 = h2['coords']
            min_height = min(h1_y2 - h1_y1, h2_y2 - h2_y1)
            vertical_match = abs(h1_y1 - h2_y1) < min_height

            if vertical_match and abs(h1_x1 - h2_x1) > COLUMN_SPLIT_THRESHOLD_X:
                left_x2 = min(h1_x2, h2_x2) if h1_x1 < h2_x1 else min(h1_x2, h2_x2)
                right_x1 = max(h1_x1, h2_x1) if h1_x1 <h2_x1 else max(h1_x1, h2_x1)
                x_split = (left_x2 + right_x1)/2
                break
        
        if x_split is not None: break 
    
    if x_split is None: return classified_sections, []

    left_column = []
    right_column = []
    for item in classified_sections:
        x_mid = (item['coords'][2] + item['coords'][3]) / 2
        if x_mid < x_split:
            left_column.append(item)
        else:
            right_column.append(item)

    left_column.sort(key=lambda x: x['coords'][0])
    right_column.sort(key=lambda x: x['coords'][0])

    return left_column, right_column

# ---------------- GROUPING LOGIC ----------------
def group_sections_by_heading(classified_sections_list):
    # Code omitted for brevity
    if not classified_sections_list: return []
    
    final_grouped_sections = []
    current_section = None
    
    for i, item in enumerate(classified_sections_list):
        item['index'] = i 

    for i in range(len(classified_sections_list)):
        item = classified_sections_list[i]
        item_label = item['label']
        item_rank = HEADING_RANK.get(item_label, 4)
        is_heading = item_rank <= 3
        
        if current_section is not None:
            terminator_rank = current_section['section_terminator_rank']
            
            if is_heading and item_rank <= terminator_rank:
                final_grouped_sections.append(current_section)
                current_section = None
                
        if current_section is None:
            if is_heading:
                h_y1, h_y2, h_x1, h_x2 = item['coords']
                current_section = {
                    'heading_label': item_label,
                    'heading_height': item['height'],
                    'heading_x_span': (h_x1, h_x2),
                    'start_coords': item['coords'],
                    'end_coords': item['coords'],
                    'content_blocks': [item],
                    'start_index': item['index'],
                    'section_terminator_rank': item_rank 
                }

        else:
            current_section['end_coords'] = item['coords']
            current_section['content_blocks'].append(item)
            

    if current_section is not None:
        final_grouped_sections.append(current_section)

    for i, section in enumerate(final_grouped_sections):
        if not section['content_blocks']: continue

        line_x1, line_x2 = section['heading_x_span']
        line_y1 = section['content_blocks'][0]['coords'][0]
        
        line_y2 = section['content_blocks'][-1]['coords'][1] 

        line_x1 += LINE_X_OFFSET
        line_x2 += LINE_X_OFFSET

        if i < len(final_grouped_sections) - 1:
            next_heading_y1 = final_grouped_sections[i + 1]['start_coords'][0]
            line_y2 = next_heading_y1

        section['vertical_line_span'] = (int(line_x1), int(line_x2), int(line_y1), int(line_y2))

        all_x1 = [block['coords'][2] for block in section['content_blocks']]
        all_x2 = [block['coords'][3] for block in section['content_blocks']]
        section['final_bounding_box'] = (int(line_y1), int(line_y2), int(min(all_x1)), int(max(all_x2)))

    return final_grouped_sections


# ---------------- HORIZONTAL LINK DRAWING ----------------
def draw_horizontal_link_lines(image_path, grouped_sections, all_blocks, all_classified_sections):
    # Code omitted for brevity
    img = cv2.imread(image_path)
    if img is None: return None
    
    img_width = img.shape[1]
    coord_to_label_map = create_coord_to_label_map(all_classified_sections)
    all_search_blocks = set(all_blocks)
    
    for section in grouped_sections:
        heading_label = section['heading_label']
        if heading_label != 'H2': continue

        h2_coords = section['content_blocks'][0]['coords']
        h2_rank = HEADING_RANK.get(heading_label) 

        h2_y1, h2_y2, h2_x1, h2_x2 = h2_coords
        y_mid = int((h2_y1 + h2_y2) /2)
        x_start = h2_x2 
        x_end = img_width 

        y_search_tolerance = 5
        possible_terminators_x = []

        for by1, by2, bx1, bx2 in all_search_blocks:
            current_coords = (by1, by2, bx1, bx2)
            if current_coords == h2_coords: continue

            if max(by1, y_mid - y_search_tolerance) < min(by2, y_mid + y_search_tolerance):
                if bx1 > x_start:
                    block_label = coord_to_label_map.get(current_coords)
                    block_rank = HEADING_RANK.get(block_label, 4)

                    if block_rank <= h2_rank: 
                        possible_terminators_x.append(bx1)

        if possible_terminators_x:
            x_end = min(possible_terminators_x)

        if x_end > x_start + 10:
            cv2.line(img, (int(x_start), y_mid), (int(x_end), y_mid),
                     HORIZONTAL_LINK_COLOR, HORIZONTAL_LINK_THICKNESS)

    return img


# ---------------- DRAWING FUNCTION (ONLY BOUNDING BOX) ----------------
def draw_final_sections(image_path, final_grouped_sections, all_blocks, margin=6):
    img = cv2.imread(image_path)
    if img is None: return None

    color_map = {'H1': H1_COLOR, 'H2': H2_COLOR, 'H3': H3_COLOR}

    def intervals_intersect(a1, a2, b1, b2):
        return not (a2 < b1 or b2 < a1)

    for section in final_grouped_sections:
        label = section['heading_label']
        color = color_map.get(label, (100, 100, 100)) 

        if 'vertical_line_span' not in section: continue
        line_x1, line_x2, line_y1, line_y2 = section['vertical_line_span']

        # NOTE: Vertical line drawing is intentionally removed here.
        # --- ADD THESE LINES TO DRAW THE VERTICAL LINE ---
        #thickness = NARROW_SECTION_LINE_THICKNESS # Defined as 5 in your constants
        
        # 1. Draw the vertical line on the left side of the section
        # cv2.line(img, (int(line_x1), int(line_y1)), 
        #          (int(line_x1), int(line_y2)), 
        #          NARROW_SECTION_LINE_COLOR, # Defined as (255, 0, 0) - Blue/Red
        #          thickness)
                 
        touching_blocks_coords = set(b['coords'] for b in section['content_blocks'])
        
        for b in all_blocks:
            by1, by2, bx1, bx2 = b
            if intervals_intersect(by1, by2, line_y1, line_y2) and \
               ((bx1 <= line_x1 and bx2 >= line_x1) or (bx1 <= line_x2 and bx2 >= line_x2) or \
                (bx1 >= line_x1 and bx2 <= line_x2)):
                touching_blocks_coords.add(b)

        touching_blocks = list(touching_blocks_coords)
        
        if touching_blocks:
            all_x1s = [int(b[2]) for b in touching_blocks]
            all_x2s = [int(b[3]) for b in touching_blocks]
            
            bbox_y1 = int(line_y1)
            bbox_y2 = int(line_y2)
            bbox_x1 = max(0, min(all_x1s))
            bbox_x2 = min(img.shape[1], max(all_x2s))
            
            cv2.rectangle(img, (bbox_x1, bbox_y1), (bbox_x2, bbox_y2), color, BOX_THICKNESS + 1)
            cv2.putText(img, label, (bbox_x1, bbox_y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, BOX_THICKNESS + 1)

    return img


# ---------------- CONTOUR-BASED TEXT BLOCK DETECTION ----------------
def group_resume_sections_by_density_white_focus(image_path):
    img = cv2.imread(image_path)
    if img is None: return []
    h_orig, w_orig = img.shape[:2]

    # 1. Grayscale Conversion
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # -----------------------------------------------------
    #  FOCUS: Binarization for WHITE Text on Dark Background
    # -----------------------------------------------------
    
    # 2a. Normal Thresholding (Captures WHITE text on dark background)
    # This captures text in dark header blocks or sidebars. Text becomes black (0).
    _, binary_normal = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 2b. INVERT: We need the text to be WHITE (255) for contour detection.
    # Inverts the colors: White text becomes white (255), dark background becomes black (0).
    binary = cv2.bitwise_not(binary_normal) 
    
    # NOTE: The variable 'binary' now holds the white-text-focused foreground mask.
    # -----------------------------------------------------

    # -----3. Dilation and Contour Detection) -----
    # ... (Kernel definition and Dilation steps remain the same) ...
    hw_ratio = h_orig / w_orig if w_orig > 0 else 0
    kernel_width = DEFAULT_KERNEL_WIDTH
    if hw_ratio > SINGLE_COLUMN_RATIO_THRESHOLD:
        kernel_width = int(w_orig * 0.04) 
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 5))
    dilated = cv2.dilate(binary, kernel, iterations=1)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    temp_img_for_composite = img.copy() 
    all_valid_bounding_boxes = [] 
    min_required_width = w_orig * WIDTH_RATIO_THRESHOLD 
    
    # ... (Contour loop remains the same) ...
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < MIN_NOISE_AREA or h < MIN_HEIGHT_THRESHOLD: continue
        
        y1, y2, x1, x2 = y, y + h, x, x + w
        all_valid_bounding_boxes.append((y1, y2, x1, x2)) 
        
        if w >= min_required_width:
            cv2.rectangle(temp_img_for_composite, (x1, y1), (x2, y2), (0, 255, 0), BOX_THICKNESS)
        else:
            cv2.line(temp_img_for_composite, (x1, y1), (x1, y2), NARROW_SECTION_LINE_COLOR, NARROW_SECTION_LINE_THICKNESS)
            cv2.line(temp_img_for_composite, (x2, y1), (x2, y2), NARROW_SECTION_LINE_COLOR, NARROW_SECTION_LINE_THICKNESS)

    all_valid_bounding_boxes.sort(key=lambda x: x[0]) 
    
    # --- DEBUGGING VISUALIZATION (Uses the 'binary' for white-text focus) ---
    binary_color = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    dilated_color = cv2.cvtColor(dilated, cv2.COLOR_GRAY2BGR)
    final_resized_composite = cv2.resize(temp_img_for_composite, (w_orig, h_orig), interpolation=cv2.INTER_AREA)
    top_row = np.hstack([img, cv2.resize(binary_color, (w_orig, h_orig))])
    bottom_row = np.hstack([cv2.resize(dilated_color, (w_orig, h_orig)), final_resized_composite])
    composite_image_2x2 = np.vstack([top_row, bottom_row])
    display_workflow_interactive(composite_image_2x2, 'Resume Segmentation Workflow (White Focus)')
    
    return all_valid_bounding_boxes


def group_resume_sections_by_density_black_focus(image_path):
    img = cv2.imread(image_path)
    if img is None: return []
    h_orig, w_orig = img.shape[:2]

    # 1. Grayscale Conversion
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # -----------------------------------------------------
    #  FOCUS: Binarization for BLACK Text on White Background
    # -----------------------------------------------------
    
    # 2a. Normal Thresholding (Captures BLACK text on white background)
    # This captures text in dark header blocks or sidebars. Text becomes black (0).
    _, binary_normal = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 2b. INVERT: We need the text to be WHITE (255) for contour detection.
    # Inverts the colors: White text becomes white (255), dark background becomes black (0).
    binary = cv2.bitwise_not(binary_normal) 
    
    # NOTE: The variable 'binary' now holds the white-text-focused foreground mask.
    # -----------------------------------------------------

    # -----3. Dilation and Contour Detection) -----
    # ... (Kernel definition and Dilation steps remain the same) ...
    hw_ratio = h_orig / w_orig if w_orig > 0 else 0
    kernel_width = DEFAULT_KERNEL_WIDTH
    if hw_ratio > SINGLE_COLUMN_RATIO_THRESHOLD:
        kernel_width = int(w_orig * 0.04) 
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 5))
    dilated = cv2.dilate(binary, kernel, iterations=1)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    temp_img_for_composite = img.copy() 
    all_valid_bounding_boxes = [] 
    min_required_width = w_orig * WIDTH_RATIO_THRESHOLD 
    
    # ... (Contour loop remains the same) ...
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < MIN_NOISE_AREA or h < MIN_HEIGHT_THRESHOLD: continue
        
        y1, y2, x1, x2 = y, y + h, x, x + w
        all_valid_bounding_boxes.append((y1, y2, x1, x2)) 
        
        if w >= min_required_width:
            cv2.rectangle(temp_img_for_composite, (x1, y1), (x2, y2), (0, 255, 0), BOX_THICKNESS)
        else:
            cv2.line(temp_img_for_composite, (x1, y1), (x1, y2), NARROW_SECTION_LINE_COLOR, NARROW_SECTION_LINE_THICKNESS)
            cv2.line(temp_img_for_composite, (x2, y1), (x2, y2), NARROW_SECTION_LINE_COLOR, NARROW_SECTION_LINE_THICKNESS)

    all_valid_bounding_boxes.sort(key=lambda x: x[0]) 
    
    # --- DEBUGGING VISUALIZATION (Uses the 'binary' for white-text focus) ---
    binary_color = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    dilated_color = cv2.cvtColor(dilated, cv2.COLOR_GRAY2BGR)
    final_resized_composite = cv2.resize(temp_img_for_composite, (w_orig, h_orig), interpolation=cv2.INTER_AREA)
    top_row = np.hstack([img, cv2.resize(binary_color, (w_orig, h_orig))])
    bottom_row = np.hstack([cv2.resize(dilated_color, (w_orig, h_orig)), final_resized_composite])
    composite_image_2x2 = np.vstack([top_row, bottom_row])
    display_workflow_interactive(composite_image_2x2, 'Resume Segmentation Workflow (White Focus)')
    
    return all_valid_bounding_boxes


# ---------------- OCR HELPER FUNCTION (CROP & DISPLAY) ----------------
def crop_and_ocr_section(image_path, bounding_box, label, margin_vertical=5, margin_horizontal=10, display_crop=True):
    """
    Crops the image, applies separate horizontal/vertical margins, displays the crop, 
    and runs Tesseract OCR with PSM=6.
    
    :param image_path: Path to the original image file.
    :param bounding_box: A tuple (y1, y2, x1, x2) defining the crop area.
    :param label: The heading label of the section (for the plot title).
    :param margin_vertical: Vertical padding in pixels.
    :param margin_horizontal: Horizontal padding in pixels.
    :param display_crop: If True, displays the cropped image using Matplotlib.
    :return: Extracted text as a string.
    """
    try:
        # Tesseract Configuration: PSM 6 (Assume a single uniform block of text)
        custom_config = r'--psm 6'
        
        img_pil = Image.open(image_path) 
        h_orig, w_orig = img_pil.height, img_pil.width
        
        y1_orig, y2_orig, x1_orig, x2_orig = bounding_box
        
        # Apply separate Horizontal and Vertical Margins
        x1_crop = max(0, x1_orig - margin_horizontal) 
        y1_crop = max(0, y1_orig - margin_vertical)
        x2_crop = min(w_orig, x2_orig + margin_horizontal) 
        y2_crop = min(h_orig, y2_orig + margin_vertical)
        
        # Crop the image: (left, upper, right, lower)
        cropped_img_pil = img_pil.crop((x1_crop, y1_crop, x2_crop, y2_crop))
        
        # Display the Cropped Section for verification
        if display_crop:
            cropped_np = np.array(cropped_img_pil) 
            plt.figure(figsize=(10, 3))
            plt.imshow(cropped_np)
            plt.title(f"Cropped Section: {label}")
            plt.axis('off')
            plt.show()
            
        # Apply OCR using the custom config
        text = pytesseract.image_to_string(cropped_img_pil, lang='eng', config=custom_config)
        return text.strip()
        
    except Exception as e:
        print(f"OCR failed for bounding box {bounding_box}: {e}")
        return f"--- OCR Failed: {e} ---"


# ---------------- MAIN OCR & SAVE FUNCTION ----------------
def process_and_save_sections(image_path, grouped_sections, output_filename="ocr_output.txt"):
    """
    Iterates through final grouped sections, performs OCR, saves to a file, 
    AND returns the full text as a string.
    """
    
    # --- OCR CONFIGURATION ---
    OCR_CROP_MARGIN_V = 10 
    OCR_CROP_MARGIN_H = 30 
    X1_LEFT_FIX_OFFSET = 30 
    # -------------------------

    print(f"\n--- Starting OCR and Text Output to '{output_filename}' ---")
    
    # Initialize a list to hold all sections of text
    full_corpus_sections = [] 
    
    with open(output_filename, 'w', encoding='utf-8') as outfile:
        
        for i, section in enumerate(grouped_sections):
            
            if 'final_bounding_box' not in section:
                continue

            label = section['heading_label']
            bounding_box = section['final_bounding_box']
            
            y1, y2, x1, x2 = bounding_box
            x1_fixed = max(0, x1 - X1_LEFT_FIX_OFFSET) 
            bounding_box_fixed = (y1, y2, x1_fixed, x2) 
            
            ocr_text = crop_and_ocr_section(
                image_path, 
                bounding_box_fixed, 
                label=f"Section {i+1}: {label}", 
                margin_vertical=OCR_CROP_MARGIN_V, 
                margin_horizontal=OCR_CROP_MARGIN_H,
                display_crop=True 
            )
            
            #  KEY CHANGE: Format the text for the corpus
            formatted_text = f"## {label} ##\n{ocr_text.strip()}\n"
            full_corpus_sections.append(formatted_text)
            
            # Write to file (for debugging/record keeping)
            outfile.write(f"## {label} Section Start ##\n")
            outfile.write(f"Bounding Box (Original): {bounding_box}, Bounding Box (Adjusted): {bounding_box_fixed}\n")
            outfile.write("--------------------------------\n")
            outfile.write(ocr_text)
            outfile.write("\n--------------------------------\n")
            outfile.write(f"## {label} Section End ##\n\n")

    print(f" OCR results successfully saved to {output_filename}")
    
    #  KEY CHANGE: Return the complete corpus text
    return "\n\n".join(full_corpus_sections)


# Make sure to update your functions in ollama_test.py to accept 'corpus' as an argument:
# def generate_extraction_prompt(corpus): ...
# def extract_data_with_ollama(corpus): ...


# ---------------- MAIN EXECUTION ----------------#
if __name__ == '__main__':
    # --- File Paths ---
    input_file_path = r"D:\Sem5\WORKSHOP2_V2_Farouk\OCR_code\29.png"   # Original input file (PDF or Image)
    temp_image_path = r"D:\Sem5\WORKSHOP2_V2_Farouk\OCR_code\temp_resume_page_1.png"      # Temp file for PDF conversion
    current_processing_path = None                  # Path used for image-based processing
    output_json_filename = r"D:\Sem5\WORKSHOP2_V2_Farouk\OCR_code\resume_extracted_data.json"
    # ------------------
    
    if not os.path.exists(input_file_path):
        print(f"\n ERROR: Input file '{input_file_path}' not found. Please ensure the file is in the correct directory.")
        # Exit or handle error
        exit()

    # --- Conditional PDF Check and Conversion ---
    if Path(input_file_path).suffix.lower() == '.pdf':
        print(f"\n Detected PDF file: {input_file_path}. Attempting to convert the first page to image...")
        
        # Convert PDF to temp image
        converted_path = convert_pdf_to_image(input_file_path, temp_image_path)
        
        if converted_path:
            current_processing_path = converted_path
        else:
            print(" Processing aborted due to failed PDF conversion.")
            # Exit or handle error
            exit()
            
    else:
        # If it's not a PDF (e.g., .png, .jpg), use the original path directly
        print(f"\n Detected image file: {input_file_path}. Proceeding directly to processing.")
        current_processing_path = input_file_path
        
    # --- Start Image Processing Workflow ---
    if current_processing_path and os.path.exists(current_processing_path):
        print(f"--- Starting Document Layout Analysis on {current_processing_path} ---")

        # 1) Find contour-based text blocks
        white_focused_boxes = group_resume_sections_by_density_white_focus(current_processing_path)
        
        # Get boxes focused on black-on-white regions (main body text)
        black_focused_boxes = group_resume_sections_by_density_black_focus(current_processing_path)

        # Combine ALL raw detected boxes into one list
        bounding_boxes = white_focused_boxes + black_focused_boxes

        # 2) Get YOLO headers
        yolo_headers = detect_yolo_headers(current_processing_path, device='cpu') # Changed to CPU for compatibility

        if bounding_boxes:
            # Prepare TEXT blocks from contour detection
            text_blocks = []
            for box_coords in bounding_boxes:
                y1, y2, x1, x2 = box_coords
                h = y2 - y1
                text_blocks.append({
                    'label': 'TEXT', 
                    'height': h, 
                    'coords': box_coords, 
                    'source': 'contour'
                })

            final_classified_sections = yolo_headers + text_blocks
            final_classified_sections = [f for f in final_classified_sections if 'coords' in f]
            final_classified_sections.sort(key=lambda b: b['coords'][0])

            # Column segmentation
            left_column_blocks, right_column_blocks = segment_into_columns(final_classified_sections)
            print(f"\n--- Column Segmentation Detected ---")
            print(f"Left Column Blocks: {len(left_column_blocks)}, Right Column Blocks: {len(right_column_blocks)}")

            # Group sections in each column
            left_grouped_sections = group_sections_by_heading(left_column_blocks)
            right_grouped_sections = group_sections_by_heading(right_column_blocks)

            final_grouped_sections = left_grouped_sections + right_grouped_sections
            final_grouped_sections.sort(key=lambda x: x['start_coords'][0])

            # Fallback: if no grouped sections, wrap all bounding boxes into one section
            if not final_grouped_sections and bounding_boxes:
                min_y1 = min(b[0] for b in bounding_boxes)
                max_y2 = max(b[1] for b in bounding_boxes)
                min_x1 = min(b[2] for b in bounding_boxes)
                max_x2 = max(b[3] for b in bounding_boxes)
                final_grouped_sections = [{
                    'heading_label': 'TEXT',
                    'content_blocks': [{'label': 'TEXT', 'coords': b, 'height': b[1]-b[0]} for b in bounding_boxes],
                    'vertical_line_span': (min_x1, max_x2, min_y1, max_y2),
                    'final_bounding_box': (min_y1, max_y2, min_x1, max_x2),
                    'start_coords': (min_y1, max_y2, min_x1, max_x2)
                }]
                print("No grouped sections detected; using single fallback section.")

            # Draw final output visualization
            final_image = draw_final_sections(current_processing_path, final_grouped_sections, bounding_boxes)
            display_workflow_interactive(final_image, 'Final Grouped Sections (Bounding Boxes Only)')
            
            # Draw horizontal links
            horizontal_link_image = draw_horizontal_link_lines(current_processing_path, final_grouped_sections, bounding_boxes, final_classified_sections)
            display_workflow_interactive(horizontal_link_image, 'Horizontal H2 Linking Lines (Hierarchical Termination)')

            #  CRITICAL STEP: Process, OCR, and RETURN the complete text corpus
            # The 'full_corpus' variable now holds the OCR-extracted text string
            full_corpus = process_and_save_sections(
                current_processing_path, 
                final_grouped_sections, 
                output_filename="resume_extracted_text.txt"
            )
            
            
           # -------------------------------------------------------------
            #  LLM EXTRACTION START (FIXED TO SAVE JSON)
            # -------------------------------------------------------------
            
            if full_corpus:
                print("\n--- Starting Ollama Extraction (LLM) ---")
                
                # Call the extraction function (returns JSON string)
                # NOTE: This call will use the num_predict: 4096 option
                json_output = extract_data_with_ollama(full_corpus) 
                
                if json_output:
                    try:
                        # 1. Parse the JSON string
                        parsed_json = json.loads(json_output)
                        
                        # 2. Save the formatted JSON to a file
                        with open(output_json_filename, 'w', encoding='utf-8') as f:
                            json.dump(parsed_json, f, indent=4)
                        
                        print(f" Final structured data saved to: {output_json_filename}")
                        
                        # 3. Print the output
                        print("\n--- Final Structured JSON Output from LLM ---")
                        print(json.dumps(parsed_json, indent=4))

                    except json.JSONDecodeError:
                        print(f" Warning: LLM output was not valid JSON. Printing raw output.")
                        print(json_output)
                else:
                    print("Extraction failed or returned no data.")

            else:
                print(" OCR failed to produce text corpus for LLM processing.")

            # --- Clean up the temporary image file if one was created ---
            if current_processing_path == temp_image_path and os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                    print(f" Cleaned up temporary file: {temp_image_path}")
                except Exception as e:
                    print(f" Warning: Failed to delete temporary file {temp_image_path}. Error: {e}")
            
        else:
            print("\n No sections were processed successfully.")
            
    else:
        print("\n Processing cancelled due to missing or invalid file path.")
