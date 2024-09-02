# upload.py
from typing import List
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
import shutil
import pdfplumber

from models import PDFPageData, TextRect


DPI = 300  # Set the resolution (DPI) for rendering images from PDFs

def upload_pdf(file: UploadFile, upload_dir: Path, images_dir: Path, dpi: int = DPI) -> (str, List[PDFPageData], dict, dict):
    file_id = str(uuid4())  # Generate a unique ID for this file
    file_path = upload_dir / f"{file_id}.pdf"
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    page_data = []
    text_rectangles_by_page = {file_id: {}}  # Store data by file_id first
    scaling_factors = {}

    with pdfplumber.open(file_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            # Render the page as an image using pdfplumber with custom DPI
            page_image = page.to_image(resolution=dpi)

            # Save the rendered image
            image_path = images_dir / f"{file_id}_page_{page_number}.jpeg"
            page_image.save(image_path)

            # Extract text rectangles from the page
            text_rects = []
            for char in page.chars:
                text = char["text"]
                if not text.strip() or not any(c.isprintable() for c in text):
                    continue

                rect = TextRect(
                    box=[char["x0"], char["top"], char["x1"], char["bottom"]],
                    text=text,
                    fontname=char["fontname"],
                    size=round(char["size"])
                )
                text_rects.append(rect)

            text_rectangles_by_page[file_id][page_number] = text_rects  # Now stored by file_id and page_number

            page_data.append(PDFPageData(
                page_number=page_number,
                image_url=f"/images/{file_id}_page_{page_number}.jpeg",
                text_rects=text_rects
            ))

            # Calculate and store scaling factors
            image_width = page_image.original.width
            image_height = page_image.original.height
            scale_x = image_width / page.width
            scale_y = image_height / page.height
            scaling_factors[(file_id, page_number)] = (scale_x, scale_y)

    return file_id, page_data, text_rectangles_by_page, scaling_factors
