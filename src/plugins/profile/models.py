from dataclasses import dataclass, field


@dataclass
class UserStats:
    total_messages: int = 0
    avg_daily: float = 0.0
    hourly_distribution: dict[int, int] = field(default_factory=dict)  # hour -> count
    top_words: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class UserProfile:
    user_id: int
    group_id: int
    stats: UserStats
    tags: list[str]
    relations: dict[int, int]  # target_user_id -> interaction_count
