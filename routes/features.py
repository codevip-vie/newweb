from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError

from models import (
    ChatMessage,
    Friendship,
    FriendRequest,
    Task,
    TaskProject,
    TaskSection,
    TaskWorkspace,
    TimetableEntry,
    User,
    UserAvatar,
    db_session,
    utc_now,
)
from uploads import (
    ALLOWED_FILE_EXTENSIONS,
    ALLOWED_FILE_MIMES,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIMES,
    UploadError,
    save_upload,
)


features_bp = Blueprint("features", __name__, url_prefix="/dashboard/features")


def _load_friends(user: User) -> list[User]:
    friends = (
        db_session.query(User)
        .join(Friendship, Friendship.friend_id == User.id)
        .filter(Friendship.user_id == user.id)
        .order_by(User.username)
        .all()
    )
    return friends


def _is_friend(user: User, peer: User) -> bool:
    if user.id == peer.id:
        return False
    friendship = (
        db_session.query(Friendship)
        .filter(Friendship.user_id == user.id, Friendship.friend_id == peer.id)
        .first()
    )
    return friendship is not None


def _get_default_workspace(user: User) -> TaskWorkspace:
    workspace = db_session.query(TaskWorkspace).filter(TaskWorkspace.user_id == user.id).order_by(TaskWorkspace.created_at).first()
    if workspace is None:
        workspace = TaskWorkspace(user_id=user.id, name="Personal Workspace")
        db_session.add(workspace)
        db_session.commit()
    return workspace


def _get_default_project(workspace: TaskWorkspace) -> TaskProject:
    project = db_session.query(TaskProject).filter(TaskProject.workspace_id == workspace.id).order_by(TaskProject.created_at).first()
    if project is None:
        project = TaskProject(workspace_id=workspace.id, name="Inbox")
        db_session.add(project)
        db_session.commit()
    return project


def _ensure_sections(project: TaskProject) -> list[TaskSection]:
    sections = db_session.query(TaskSection).filter(TaskSection.project_id == project.id).order_by(TaskSection.id).all()
    if not sections:
        default_sections = ["To Do", "In Progress", "Done"]
        for name in default_sections:
            sections.append(TaskSection(project_id=project.id, name=name))
        db_session.add_all(sections)
        db_session.commit()
    return sections


def _avatar_directory() -> Path:
    return Path(current_app.config["AVATAR_UPLOAD_DIR"])


def _chat_directory() -> Path:
    return Path(current_app.config["CHAT_UPLOAD_DIR"])


@features_bp.route("/avatar", methods=["GET", "POST"])
@login_required
def avatar_library():
    avatar = (
        db_session.query(UserAvatar)
        .filter(UserAvatar.user_id == current_user.id)
        .order_by(UserAvatar.created_at.desc())
        .first()
    )
    avatar_url = None
    if avatar is not None:
        avatar_url = url_for("features.avatar_file", filename=avatar.filename)

    errors: list[str] = []
    if request.method == "POST":
        image_file = request.files.get("avatar")
        try:
            saved = save_upload(
                image_file,
                destination=_avatar_directory(),
                allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                allowed_mimes=ALLOWED_IMAGE_MIMES,
                max_bytes=current_app.config["MAX_IMAGE_BYTES"],
                label="Avatar image",
            )
            user_avatar = UserAvatar(
                user_id=current_user.id,
                filename=saved.filename,
                original_name=saved.original_name,
                size=saved.size,
            )
            db_session.add(user_avatar)
            db_session.commit()
            flash("Avatar updated successfully.", "success")
            return redirect(url_for("features.avatar_library"))
        except UploadError as exc:
            errors.append(str(exc))
        except SQLAlchemyError:
            db_session.rollback()
            errors.append("Avatar could not be saved. Please try again.")

    return render_template(
        "features/avatar.html",
        avatar_url=avatar_url,
        errors=errors,
    )


@features_bp.route("/avatar-file/<path:filename>")
@login_required
def avatar_file(filename: str):
    return send_from_directory(_avatar_directory(), filename)


@features_bp.route("/friends", methods=["GET", "POST"])
@login_required
def friends():
    query_text = request.args.get("q", "").strip()
    action = request.form.get("action")
    target_id = request.form.get("target_id")
    errors: list[str] = []

    if action and target_id:
        target_user = db_session.get(User, int(target_id)) if target_id.isdigit() else None
        if target_user is None or target_user.id == current_user.id:
            errors.append("Invalid user selected.")
        else:
            try:
                if action == "send_request":
                    existing = (
                        db_session.query(FriendRequest)
                        .filter(
                            FriendRequest.sender_id == current_user.id,
                            FriendRequest.receiver_id == target_user.id,
                        )
                        .first()
                    )
                    if existing:
                        errors.append("Request already sent.")
                    elif _is_friend(current_user, target_user):
                        errors.append("User is already a friend.")
                    else:
                        db_session.add(
                            FriendRequest(
                                sender_id=current_user.id,
                                receiver_id=target_user.id,
                                status="pending",
                            )
                        )
                        db_session.commit()
                        flash("Friend request sent.", "success")
                        return redirect(url_for("features.friends"))
                elif action == "cancel_request":
                    request_item = (
                        db_session.query(FriendRequest)
                        .filter(
                            FriendRequest.sender_id == current_user.id,
                            FriendRequest.receiver_id == target_user.id,
                            FriendRequest.status == "pending",
                        )
                        .first()
                    )
                    if request_item:
                        db_session.delete(request_item)
                        db_session.commit()
                        flash("Friend request cancelled.", "success")
                        return redirect(url_for("features.friends"))
                    errors.append("No pending friend request found.")
                elif action == "accept_request":
                    request_item = (
                        db_session.query(FriendRequest)
                        .filter(
                            FriendRequest.sender_id == target_user.id,
                            FriendRequest.receiver_id == current_user.id,
                            FriendRequest.status == "pending",
                        )
                        .first()
                    )
                    if request_item:
                        db_session.add_all(
                            [
                                Friendship(user_id=current_user.id, friend_id=target_user.id),
                                Friendship(user_id=target_user.id, friend_id=current_user.id),
                            ]
                        )
                        db_session.delete(request_item)
                        db_session.commit()
                        flash("Friend request accepted.", "success")
                        return redirect(url_for("features.friends"))
                    errors.append("No pending request to accept.")
                elif action == "decline_request":
                    request_item = (
                        db_session.query(FriendRequest)
                        .filter(
                            FriendRequest.sender_id == target_user.id,
                            FriendRequest.receiver_id == current_user.id,
                            FriendRequest.status == "pending",
                        )
                        .first()
                    )
                    if request_item:
                        request_item.status = "declined"
                        db_session.commit()
                        flash("Friend request declined.", "success")
                        return redirect(url_for("features.friends"))
                    errors.append("No pending request to decline.")
                elif action == "remove_friend":
                    friend_a = (
                        db_session.query(Friendship)
                        .filter(
                            Friendship.user_id == current_user.id,
                            Friendship.friend_id == target_user.id,
                        )
                        .first()
                    )
                    friend_b = (
                        db_session.query(Friendship)
                        .filter(
                            Friendship.user_id == target_user.id,
                            Friendship.friend_id == current_user.id,
                        )
                        .first()
                    )
                    if friend_a:
                        db_session.delete(friend_a)
                    if friend_b:
                        db_session.delete(friend_b)
                    db_session.commit()
                    flash("Friend removed.", "success")
                    return redirect(url_for("features.friends"))
            except SQLAlchemyError:
                db_session.rollback()
                errors.append("Unable to update friendship status. Please try again.")

    search_results: list[User] = []
    if query_text:
        query = db_session.query(User).filter(
            User.id != current_user.id,
            or_(User.username.ilike(f"%{query_text}%"), User.email.ilike(f"%{query_text}%"))
        )
        search_results = query.order_by(User.username).limit(12).all()

    friends = _load_friends(current_user)
    outgoing_requests = (
        db_session.query(FriendRequest)
        .filter(FriendRequest.sender_id == current_user.id, FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at.desc())
        .all()
    )
    incoming_requests = (
        db_session.query(FriendRequest)
        .filter(FriendRequest.receiver_id == current_user.id, FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at.desc())
        .all()
    )

    return render_template(
        "features/friends.html",
        query_text=query_text,
        search_results=search_results,
        friends=friends,
        outgoing_requests=outgoing_requests,
        incoming_requests=incoming_requests,
        errors=errors,
    )


@features_bp.route("/chat")
@login_required
def chat():
    friends = _load_friends(current_user)
    return render_template("features/chat.html", friends=friends, active_peer=None, messages=[], unread_counts={})


@features_bp.route("/chat/<int:peer_id>", methods=["GET", "POST"])
@login_required
def chat_conversation(peer_id: int):
    peer = db_session.get(User, peer_id)
    if peer is None or not _is_friend(current_user, peer):
        abort(404)

    if request.method == "POST":
        body = request.form.get("body", "").strip()
        attachment = request.files.get("attachment")
        if not body and (attachment is None or not attachment.filename):
            flash("Enter a message or attach a file.", "error")
            return redirect(url_for("features.chat_conversation", peer_id=peer_id))

        attachment_filename = None
        attachment_original_name = None
        attachment_size = None
        if attachment and attachment.filename:
            try:
                saved = save_upload(
                    attachment,
                    destination=_chat_directory(),
                    allowed_extensions=ALLOWED_FILE_EXTENSIONS,
                    allowed_mimes=ALLOWED_FILE_MIMES,
                    max_bytes=current_app.config["MAX_IMAGE_BYTES"] * 4,
                    label="Chat attachment",
                )
                attachment_filename = saved.filename
                attachment_original_name = saved.original_name
                attachment_size = saved.size
            except UploadError as exc:
                flash(str(exc), "error")
                return redirect(url_for("features.chat_conversation", peer_id=peer_id))

        message = ChatMessage(
            sender_id=current_user.id,
            receiver_id=peer.id,
            body=body or None,
            attachment_filename=attachment_filename,
            attachment_original_name=attachment_original_name,
            attachment_size=attachment_size,
            created_at=utc_now(),
        )
        db_session.add(message)
        db_session.commit()
        return redirect(url_for("features.chat_conversation", peer_id=peer_id))

    messages = (
        db_session.query(ChatMessage)
        .filter(
            or_(
                and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == peer.id),
                and_(ChatMessage.sender_id == peer.id, ChatMessage.receiver_id == current_user.id),
            )
        )
        .order_by(ChatMessage.created_at)
        .all()
    )
    last_message = messages[-1] if messages else None
    for item in messages:
        if item.receiver_id == current_user.id and not item.is_read:
            item.is_read = True
    db_session.commit()

    friends = _load_friends(current_user)
    unread_counts = {
        friend.id: db_session.query(ChatMessage)
        .filter(
            ChatMessage.sender_id == friend.id,
            ChatMessage.receiver_id == current_user.id,
            ChatMessage.is_read == False,
        )
        .count()
        for friend in friends
    }

    return render_template(
        "features/chat.html",
        friends=friends,
        active_peer=peer,
        messages=messages,
        last_message=last_message,
        unread_counts=unread_counts,
    )


@features_bp.route("/chat/<int:peer_id>/poll")
@login_required
def chat_poll(peer_id: int):
    peer = db_session.get(User, peer_id)
    if peer is None or not _is_friend(current_user, peer):
        return jsonify({"updated_at": None}), 404

    last_message = (
        db_session.query(ChatMessage)
        .filter(
            or_(
                and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == peer.id),
                and_(ChatMessage.sender_id == peer.id, ChatMessage.receiver_id == current_user.id),
            )
        )
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    return jsonify(
        {
            "updated_at": last_message.created_at.isoformat() if last_message else None,
            "last_message_id": last_message.id if last_message else None,
            "sender_id": last_message.sender_id if last_message else None,
        }
    )


@features_bp.route("/todo", methods=["GET", "POST"])
@login_required
def todo():
    view_mode = request.args.get("view", "list")
    search_query = request.args.get("q", "").strip()
    workspace = _get_default_workspace(current_user)
    project = _get_default_project(workspace)
    sections = _ensure_sections(project)
    errors: list[str] = []

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "Medium")
        due_date = request.form.get("due_date") or None
        labels = request.form.get("labels", "").strip()
        if not title:
            errors.append("Task title is required.")
        if not errors:
            task = Task(
                user_id=current_user.id,
                section_id=sections[0].id,
                title=title,
                description=description or None,
                priority=priority,
                due_date=datetime.fromisoformat(due_date) if due_date else None,
                labels=labels or None,
                is_complete=False,
                status="To Do",
                created_at=utc_now(),
            )
            db_session.add(task)
            try:
                db_session.commit()
                flash("Task created.", "success")
                return redirect(url_for("features.todo"))
            except SQLAlchemyError:
                db_session.rollback()
                errors.append("Unable to create task. Please try again.")

    query = db_session.query(Task).filter(Task.user_id == current_user.id)
    if search_query:
        query = query.filter(Task.title.ilike(f"%{search_query}%"))
    tasks = query.order_by(Task.created_at.desc()).all()
    return render_template(
        "features/todo.html",
        view_mode=view_mode,
        search_query=search_query,
        sections=sections,
        tasks=tasks,
        errors=errors,
    )


@features_bp.route("/todo/<int:task_id>/toggle", methods=["POST"])
@login_required
def todo_toggle(task_id: int):
    task = db_session.get(Task, task_id)
    if task is None or task.user_id != current_user.id:
        abort(404)
    task.is_complete = not task.is_complete
    task.status = "Done" if task.is_complete else "To Do"
    db_session.commit()
    return redirect(url_for("features.todo"))


@features_bp.route("/todo/<int:task_id>/delete", methods=["POST"])
@login_required
def todo_delete(task_id: int):
    task = db_session.get(Task, task_id)
    if task is None or task.user_id != current_user.id:
        abort(404)
    db_session.delete(task)
    db_session.commit()
    return redirect(url_for("features.todo"))


@features_bp.route("/timetable", methods=["GET", "POST"])
@login_required
def timetable():
    period = request.args.get("period", "week")
    errors: list[str] = []

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        entry_type = request.form.get("entry_type", "Work")
        color = request.form.get("color", "#7C3AED")
        repeat_weekly = bool(request.form.get("repeat_weekly"))
        if not title:
            errors.append("Entry title is required.")
        if not start_time or not end_time:
            errors.append("Start time and end time are required.")
        if start_time and end_time and start_time >= end_time:
            errors.append("End time must be after start time.")
        if not errors:
            entry = TimetableEntry(
                user_id=current_user.id,
                title=title,
                description=description or None,
                start_time=datetime.fromisoformat(start_time),
                end_time=datetime.fromisoformat(end_time),
                entry_type=entry_type,
                color=color,
                repeat_weekly=repeat_weekly,
                created_at=utc_now(),
            )
            db_session.add(entry)
            try:
                db_session.commit()
                flash("Timetable entry created.", "success")
                return redirect(url_for("features.timetable"))
            except SQLAlchemyError:
                db_session.rollback()
                errors.append("Unable to create schedule entry. Please try again.")

    entries = (
        db_session.query(TimetableEntry)
        .filter(TimetableEntry.user_id == current_user.id)
        .order_by(TimetableEntry.start_time)
        .all()
    )
    return render_template(
        "features/timetable.html",
        period=period,
        entries=entries,
        errors=errors,
    )


@features_bp.route("/timetable/<int:entry_id>/delete", methods=["POST"])
@login_required
def timetable_delete(entry_id: int):
    entry = db_session.get(TimetableEntry, entry_id)
    if entry is None or entry.user_id != current_user.id:
        abort(404)
    db_session.delete(entry)
    db_session.commit()
    return redirect(url_for("features.timetable"))
