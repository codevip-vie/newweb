from __future__ import annotations

from datetime import datetime
from typing import List

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, scoped_session, sessionmaker

ADMIN_USERNAMES = frozenset({"admin_default", "admin_default_clone", "admin_default_third"})


def utc_now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


db_session = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)
)
Base.query = db_session.query_property()
engine: Engine | None = None


class User(UserMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    posters: Mapped[List["Poster"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    movies: Mapped[List["Movie"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    avatars: Mapped[List["UserAvatar"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    friend_requests_sent: Mapped[List["FriendRequest"]] = relationship(
        back_populates="sender",
        foreign_keys="FriendRequest.sender_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    friend_requests_received: Mapped[List["FriendRequest"]] = relationship(
        back_populates="receiver",
        foreign_keys="FriendRequest.receiver_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    friendships: Mapped[List["Friendship"]] = relationship(
        back_populates="user",
        foreign_keys="Friendship.user_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    messages_sent: Mapped[List["ChatMessage"]] = relationship(
        back_populates="sender",
        foreign_keys="ChatMessage.sender_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    messages_received: Mapped[List["ChatMessage"]] = relationship(
        back_populates="receiver",
        foreign_keys="ChatMessage.receiver_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    poster_comments: Mapped[List["PosterComment"]] = relationship(
        back_populates="user",
        foreign_keys="PosterComment.user_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    movie_comments: Mapped[List["MovieComment"]] = relationship(
        back_populates="user",
        foreign_keys="MovieComment.user_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    workspaces: Mapped[List["TaskWorkspace"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    timetable_entries: Mapped[List["TimetableEntry"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    status: Mapped["UserStatus"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_admin_role(self) -> bool:
        if self.username in ADMIN_USERNAMES:
            return True
        return self.role == "admin" or self.is_admin


class Founder(Base):
    __tablename__ = "founders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    role: Mapped[str] = mapped_column(String(140), nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False)
    image_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drive_account_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class Poster(Base):
    __tablename__ = "posters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    image_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    image_original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    image_size: Mapped[int] = mapped_column(Integer, nullable=False)
    drive_account_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    owner: Mapped[User] = relationship(back_populates="posters")
    comments: Mapped[List["PosterComment"]] = relationship(
        back_populates="poster",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cover_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    cover_original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cover_size: Mapped[int] = mapped_column(Integer, nullable=False)
    drive_account_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    video_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    video_original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    video_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    owner: Mapped[User] = relationship(back_populates="movies")
    comments: Mapped[List["MovieComment"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserAvatar(Base):
    __tablename__ = "user_avatars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="avatars")


class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    receiver_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    sender: Mapped[User] = relationship(
        back_populates="friend_requests_sent", foreign_keys=[sender_id]
    )
    receiver: Mapped[User] = relationship(
        back_populates="friend_requests_received", foreign_keys=[receiver_id]
    )


class Friendship(Base):
    __tablename__ = "friendships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    friend_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    user: Mapped[User] = relationship(
        back_populates="friendships", foreign_keys=[user_id]
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    receiver_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_by_sender: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_by_receiver: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sender: Mapped[User] = relationship(
        back_populates="messages_sent", foreign_keys=[sender_id]
    )
    receiver: Mapped[User] = relationship(
        back_populates="messages_received", foreign_keys=[receiver_id]
    )


class TaskWorkspace(Base):
    __tablename__ = "task_workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="workspaces")
    projects: Mapped[List["TaskProject"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )


class TaskProject(Base):
    __tablename__ = "task_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("task_workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    workspace: Mapped[TaskWorkspace] = relationship(back_populates="projects")
    sections: Mapped[List["TaskSection"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class TaskSection(Base):
    __tablename__ = "task_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("task_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    project: Mapped[TaskProject] = relationship(back_populates="sections")
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="section", cascade="all, delete-orphan", passive_deletes=True
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_id: Mapped[int] = mapped_column(
        ForeignKey("task_sections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="To Do", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False, index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    labels: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="tasks")
    section: Mapped[TaskSection] = relationship(back_populates="tasks")


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(40), default="Work", nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#7C3AED", nullable=False)
    repeat_weekly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    owner: Mapped[User] = relationship(back_populates="timetable_entries")


class PosterComment(Base):
    __tablename__ = "poster_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poster_id: Mapped[int] = mapped_column(
        ForeignKey("posters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    poster: Mapped[Poster] = relationship(back_populates="comments")
    user: Mapped[User] = relationship(back_populates="poster_comments")


class MovieComment(Base):
    __tablename__ = "movie_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    movie: Mapped[Movie] = relationship(back_populates="comments")
    user: Mapped[User] = relationship(back_populates="movie_comments")


class UserStatus(Base):
    __tablename__ = "user_statuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="status")


def init_engine(database_uri: str, engine_options: dict[str, object] | None = None) -> Engine:
    global engine
    engine = create_engine(database_uri, **(engine_options or {}))

    if database_uri.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    db_session.configure(bind=engine)
    return engine


def init_db() -> None:
    if engine is None:
        raise RuntimeError("Database engine has not been configured.")
    Base.metadata.create_all(bind=engine)

    if engine.dialect.name == "sqlite":
        inspector = inspect(engine)
        columns = [column["name"] for column in inspector.get_columns("users")]
        if "is_admin" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
        if "role" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"))
        if "is_active" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))

        for table_name in ("founders", "posters", "movies"):
            columns = [column["name"] for column in inspector.get_columns(table_name)]
            if "drive_account_index" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "ALTER TABLE %s ADD COLUMN drive_account_index INTEGER NOT NULL DEFAULT 0"
                            % table_name
                        )
                    )
