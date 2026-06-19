"""Re-export Question from the combined module so `from app.models.question import Question` works."""
from app.models.exam import Question, QuestionOption  # noqa: F401
