from pydantic import BaseModel, Field


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    body: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    tag_list: list[str] = Field(default_factory=list)


class ArticleOut(BaseModel):
    id: int
    slug: str
    title: str
    description: str
    body: str
    summary: str
    author_id: int
    created_at: str
    updated_at: str
    tag_list: list[str] = Field(default_factory=list)
    favorites_count: int = 0
