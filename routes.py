from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from . import crud
from .database import get_db
from .gemini_flash_generator import generate_nutrition_tip_with_flash
from .gemini_generator import generate_workout_gemini
from .schemas import FeedbackRequest, UserInput
from .updated_plan import update_workout_plan


router = APIRouter()
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@router.post("/generate-workout", response_class=HTMLResponse)
def generate_workout(
    request: Request,
    username: str = Form(...),
    user_id: str = Form(...),
    age: int = Form(...),
    weight: float = Form(...),
    goal: str = Form(...),
    intensity: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        data = UserInput.model_validate({
            "username": username.strip(),
            "user_id": user_id.strip(),
            "age": age,
            "weight": weight,
            "goal": goal,
            "intensity": intensity
        })
    except ValidationError as error:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": error.errors()[0]["msg"]},
            status_code=422
        )

    if crud.get_user(db, data.user_id):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": "That user ID is already registered."},
            status_code=409
        )

    plan = generate_workout_gemini(
        data.username,
        data.age,
        data.weight,
        data.goal,
        data.intensity
    )
    tip = generate_nutrition_tip_with_flash(data.goal)
    user = crud.save_user(db, data)
    crud.save_plan(db, user, plan, tip)

    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "user": user,
            "workout_plan": plan,
            "nutrition_tip": tip,
            "updated": False
        }
    )


@router.get("/view-all-users", response_class=HTMLResponse)
def view_all_users(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="all_users.html",
        context={"users": crud.get_all_users(db)}
    )


@router.post("/submit-feedback", response_class=HTMLResponse)
def submit_feedback(
    request: Request,
    user_id: str = Form(...),
    feedback: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        data = FeedbackRequest.model_validate({
            "user_id": user_id.strip(),
            "feedback": feedback.strip()
        })
    except ValidationError as error:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": error.errors()[0]["msg"]},
            status_code=422
        )

    user = crud.get_user(db, data.user_id)
    if user is None:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": "User not found."},
            status_code=404
        )

    plan = update_workout_plan(
        user.original_plan,
        data.feedback,
        user.goal,
        user.intensity
    )
    crud.update_plan(db, user, plan, data.feedback)

    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "user": user,
            "workout_plan": plan,
            "nutrition_tip": user.nutrition_tip,
            "updated": True
        }
    )


@router.post("/delete-user/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db)):
    crud.delete_user(db, user_id)
    return RedirectResponse(url="/view-all-users", status_code=303)