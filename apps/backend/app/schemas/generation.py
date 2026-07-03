from pydantic import BaseModel


class GeneratedFile(BaseModel):
    filename: str
    content: str


class GenerationResult(BaseModel):
    notes: str
    files: list[GeneratedFile]
