"""
Pydantic data models for ufcstats.com entities.
Compatible with Python 3.10+ and Pydantic v2.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

class Event(BaseModel):
    """UFC Event entity."""

    model_config = ConfigDict()

    event_id: str = Field(description="Unique event ID from URL")
    url: str = Field(description="Full URL to event page")
    name: str = Field(description="Event title, e.g., 'UFC 309'")
    event_date: Optional[date] = Field(default=None, description="Event date")
    location: Optional[str] = Field(default=None, description="City, Country")
    fights_count: int = Field(default=0, description="Total fights in event")

Event.model_rebuild()


# ---------------------------------------------------------------------------
# Fighter
# ---------------------------------------------------------------------------

class Fighter(BaseModel):
    """UFC Fighter profile entity."""

    model_config = ConfigDict()

    fighter_id: str = Field(description="Unique fighter ID from URL")
    url: str = Field(description="Full URL to profile page")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nickname: Optional[str] = None

    # Physical stats
    height_cm: Optional[float] = Field(default=None, description="Height in centimeters")
    weight_kg: Optional[float] = Field(default=None, description="Weight in kilograms")
    reach_cm: Optional[float] = Field(default=None, description="Reach in centimeters")
    stance: Optional[str] = Field(default=None, description="Orthodox/Southpaw/Switch")
    dob: Optional[date] = Field(default=None, description="Date of birth")

    # Record
    wins: int = 0
    losses: int = 0
    draws: int = 0
    no_contests: int = 0

    # Career statistics
    slpm: Optional[float] = Field(default=None, description="Significant Strikes Landed Per Minute")
    str_acc: Optional[float] = Field(default=None, description="Striking Accuracy %")
    sapm: Optional[float] = Field(default=None, description="Significant Strikes Absorbed Per Minute")
    str_def: Optional[float] = Field(default=None, description="Strike Defence %")
    td_avg: Optional[float] = Field(default=None, description="Takedown Average per 15 min")
    td_acc: Optional[float] = Field(default=None, description="Takedown Accuracy %")
    td_def: Optional[float] = Field(default=None, description="Takedown Defence %")
    sub_avg: Optional[float] = Field(default=None, description="Submission Attempts per 15 min")

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) or "Unknown"

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.draws}"

Fighter.model_rebuild()


# ---------------------------------------------------------------------------
# Fight
# ---------------------------------------------------------------------------

class Fight(BaseModel):
    """UFC Fight entity."""

    model_config = ConfigDict()

    fight_id: str = Field(description="Unique fight ID from URL")
    url: str = Field(description="Full URL to fight page")
    event_id: str = Field(description="Parent event ID")

    fighter1_id: Optional[str] = None
    fighter1_name: Optional[str] = None
    fighter2_id: Optional[str] = None
    fighter2_name: Optional[str] = None

    winner_id: Optional[str] = Field(default=None, description="Winner fighter ID")
    outcome: Optional[str] = Field(default=None, description="W/L/D/NC outcome")
    method: Optional[str] = Field(default=None, description="KO/TKO, Submission, Decision")
    method_detail: Optional[str] = None
    round: Optional[int] = None
    time: Optional[str] = None
    time_format: Optional[str] = None
    referee: Optional[str] = None
    weight_class: Optional[str] = None
    title_fight: bool = False
    is_main_event: bool = False
    bonus: Optional[str] = None

Fight.model_rebuild()


# ---------------------------------------------------------------------------
# Fight Statistics (totals)
# ---------------------------------------------------------------------------

class FighterFightStats(BaseModel):
    """Statistics for one fighter in a specific fight (totals)."""

    model_config = ConfigDict()

    fight_id: str
    fighter_id: Optional[str] = None
    fighter_name: Optional[str] = None
    corner: str  # 'red' or 'blue'

    kd: int = 0
    sig_str_landed: int = 0
    sig_str_attempted: int = 0
    total_str_landed: int = 0
    total_str_attempted: int = 0
    td_landed: int = 0
    td_attempted: int = 0
    sub_att: int = 0
    rev: int = 0
    ctrl_seconds: int = 0

    sig_head_landed: int = 0
    sig_head_attempted: int = 0
    sig_body_landed: int = 0
    sig_body_attempted: int = 0
    sig_leg_landed: int = 0
    sig_leg_attempted: int = 0

    sig_distance_landed: int = 0
    sig_distance_attempted: int = 0
    sig_clinch_landed: int = 0
    sig_clinch_attempted: int = 0
    sig_ground_landed: int = 0
    sig_ground_attempted: int = 0

    @property
    def sig_str_accuracy(self) -> Optional[float]:
        if self.sig_str_attempted > 0:
            return round(self.sig_str_landed / self.sig_str_attempted * 100, 1)
        return None

    @property
    def td_accuracy(self) -> Optional[float]:
        if self.td_attempted > 0:
            return round(self.td_landed / self.td_attempted * 100, 1)
        return None

FighterFightStats.model_rebuild()


# ---------------------------------------------------------------------------
# Round Statistics
# ---------------------------------------------------------------------------

class RoundStats(FighterFightStats):
    """Statistics for one fighter in a specific round."""

    round_number: int = Field(description="Round number (1, 2, 3...)")

RoundStats.model_rebuild()
