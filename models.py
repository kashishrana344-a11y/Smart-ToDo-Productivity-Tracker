"""Domain models and extensible priority calculation for Smart Productivity."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta

@dataclass
class Task:
    """A task record with controlled status and priority changes."""
    id: int | None
    title: str
    category: str = "General"
    deadline: str = ""
    estimated_minutes: int = 30
    notes: str = ""
    completed: bool = False
    created_at: str = ""
    priority_override: str = "Auto"
    completed_at: str = ""
    def mark_complete(self):
        self.completed = True
        self.completed_at = datetime.now().isoformat(timespec="seconds")
    def mark_incomplete(self):
        self.completed = False
        self.completed_at = ""
    def set_priority(self, priority):
        if priority not in {"Auto", "Low", "Medium", "High"}: raise ValueError("Priority must be Auto, Low, Medium, or High")
        self.priority_override = priority

class PriorityStrategy(ABC):
    """Abstraction for interchangeable task-priority policies."""
    @abstractmethod
    def calculate(self, task: Task, today: date | None = None) -> str: ...

class DeadlinePriorityStrategy(PriorityStrategy):
    """Polymorphic default: urgency rises near a deadline and for long tasks."""
    def calculate(self, task, today=None):
        if task.priority_override != "Auto": return task.priority_override
        if task.completed: return "Low"
        if not task.deadline: return "Medium" if task.estimated_minutes >= 90 else "Low"
        try: days_left = (date.fromisoformat(task.deadline) - (today or date.today())).days
        except ValueError: return "Medium"
        if days_left <= 1: return "High"
        if days_left <= 3 or task.estimated_minutes >= 120: return "Medium"
        return "Low"

class TaskRepository(ABC):
    """Abstract storage contract used by UI and services."""
    @abstractmethod
    def list_tasks(self, include_completed=True): ...
    @abstractmethod
    def save_task(self, task): ...
    @abstractmethod
    def delete_task(self, task_id): ...


def completion_streak(tasks, today=None):
    """Number of consecutive days (ending today, or yesterday) with at least one completed task."""
    today = today or date.today()
    days = {t.completed_at[:10] for t in tasks if t.completed and t.completed_at}
    day = today if today.isoformat() in days else today - timedelta(days=1)
    streak = 0
    while day.isoformat() in days:
        streak += 1
        day -= timedelta(days=1)
    return streak
