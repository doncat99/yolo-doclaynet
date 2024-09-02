# models.py
from pydantic import BaseModel, Field
from typing import List

class LabelBox(BaseModel):
    label: str = Field(example="Text", description="Label of the object")
    box: list[float] = Field(
        example=[0.0, 0.0, 0.0, 0.0], description="Bounding box coordinates"
    )

class TextRect(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    text: str = Field(default="", description="Extracted text within the rectangle")
    fontname: str = Field(default="", description="Font name of the text")
    size: float = Field(default=0.0, description="Font size of the text")

class PDFPageData(BaseModel):
    page_number: int
    image_url: str
    text_rects: List[TextRect]

class CompareResult(BaseModel):
    inside: list[TextRect]
    outside: list[TextRect]

class ReclassifyResult(BaseModel):
    reclassified: list[LabelBox]

class FileIdRequest(BaseModel):
    file_id: str
    page_number: int  # Include page_number in the request to compare specific pages
