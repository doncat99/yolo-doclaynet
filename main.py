
from pathlib import Path
from typing import List

import uvicorn
from loguru import logger
from fastapi import FastAPI, UploadFile, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models import LabelBox, PDFPageData, CompareResult, FileIdRequest
from upload import upload_pdf
from detect import detect_layout
from compare import compare_layout
from reclassify import reclassify_layout

# Directories to store uploaded PDFs and converted images
UPLOAD_DIR = Path("uploads")
IMAGES_DIR = Path("images")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Serve static files from the "static" and "images" directories
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")

# Store layout data and text rectangles by page
app.state.layout_data = {}  # Stores layout rectangles detected by YOLO
app.state.text_data = {}  # Stores text rectangles extracted from PDF by page
app.state.scaling_factors = {}  # Stores scaling factors for each page
app.state.comparison_results = {}  # Store comparison results


@app.post("/upload-pdf/", response_model=List[PDFPageData])
async def upload(file: UploadFile):
    # Call the upload logic function and get all necessary data
    file_id, page_data, app.state.text_data, app.state.scaling_factors = upload_pdf(file, UPLOAD_DIR, IMAGES_DIR)
    return page_data

@app.post("/api/detect", response_model=List[LabelBox])
def detect(image: UploadFile = Form(...), file_id: str = Form(...), page_number: int = Form(...)):
    logger.info(f"Received image for detection: {image.filename} with file_id: {file_id} and page_number: {page_number}")

    image_data = image.file.read()
    label_boxes = detect_layout(image_data)

    if not label_boxes:
        raise HTTPException(status_code=400, detail="Detection failed")

    if file_id not in app.state.layout_data:
        app.state.layout_data[file_id] = {}

    app.state.layout_data[file_id][page_number] = label_boxes  # Store detected layout rectangles by page
    logger.info(f"Layout data stored for file_id: {file_id} and page_number: {page_number}")
    return label_boxes

@app.post("/compare", response_model=CompareResult)
def compare(request: FileIdRequest):
    file_id = request.file_id
    page_number = request.page_number
    logger.info(f"Received file_id for comparison: {file_id} and page_number: {page_number}")

    if file_id not in app.state.layout_data or file_id not in app.state.text_data:
        logger.error(f"File ID {file_id} not found in layout_data or text_data.")
        raise HTTPException(status_code=400, detail="No layout or text data available for this file.")

    result = compare_layout(file_id, page_number, app.state.layout_data, app.state.text_data, app.state.scaling_factors, OUTPUT_DIR)
    app.state.comparison_results[(file_id, page_number)] = result

    return CompareResult(inside=result["inside"], outside=result["outside"])

@app.post("/reclassify", response_model=List[LabelBox])
def reclassify(request: FileIdRequest):
    file_id = request.file_id
    page_number = request.page_number

    # Call the reclassify function from reclassify.py
    label_boxes = reclassify_layout(file_id, page_number, app.state.comparison_results, app.state.layout_data)

    return label_boxes

@app.get("/get-image/{file_id}/{page_number}")
async def get_image(file_id: str, page_number: int):
    image_path = Path(IMAGES_DIR) / f"{file_id}_page_{page_number}.jpeg"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    return FileResponse(image_path)

# Serve the index.html file
@app.get("/", response_class=FileResponse)
async def main():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
