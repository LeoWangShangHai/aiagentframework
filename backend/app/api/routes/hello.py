from fastapi import APIRouter

router = APIRouter()


@router.get("/hello")
def hello(name: str = "World") -> dict:
    return {"message": f"Hello, {name}!"}
