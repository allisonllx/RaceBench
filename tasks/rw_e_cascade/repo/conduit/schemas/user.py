from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=1)
    email: str = Field(min_length=3)
    bio: str = ""
    image: str = ""


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    bio: str
    image: str
