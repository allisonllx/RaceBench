from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


class CommentOut(BaseModel):
    id: int
    body: str
    article_id: int
    author_id: int
    created_at: str
    article_slug: str = ""
