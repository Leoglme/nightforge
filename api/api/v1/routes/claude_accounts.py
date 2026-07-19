"""
Claude accounts vault — CRUD, credentials reveal, usage refresh, account pick.

Mirrors ``cursor_accounts.py``, but Claude's OAuth usage API accepts a bare bearer
token directly (no browser cookie needed), so usage refresh never requires an online
agent — only the pinned "machine" card and the login capture flow do.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from models.claude_account import ClaudeAccount
from models.machine import Machine
from models.user import User
from schemas.claude_account import (
    ClaudeAccountCreate,
    ClaudeAccountCredentials,
    ClaudeAccountResponse,
    ClaudeAccountUpdate,
    ClaudeAccountsOverview,
    MachineClaudeUsage,
)
from services.agent_hub import agent_hub
from services.auth_service import get_current_active_user
from services.claude_usage_service import (
    email_from_oauth,
    fetch_claude_usage,
    pick_best_claude_account,
)
from services.encryption_service import encryption_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claude-accounts", tags=["claude-accounts"])


def _to_response(account: ClaudeAccount) -> ClaudeAccountResponse:
    return ClaudeAccountResponse(
        id=account.id,
        label=account.label,
        email=account.email,
        has_password=bool(account.password_encrypted),
        has_oauth=bool(account.oauth_encrypted),
        five_hour_utilization=account.five_hour_utilization,
        seven_day_utilization=account.seven_day_utilization,
        seven_day_opus_utilization=account.seven_day_opus_utilization,
        resets_at=account.resets_at,
        last_checked_at=account.last_checked_at,
        last_error=account.last_error,
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _get_owned(db: Session, user_id: int, account_id: int) -> ClaudeAccount:
    account = (
        db.query(ClaudeAccount)
        .filter(ClaudeAccount.id == account_id, ClaudeAccount.user_id == user_id)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    return account


def _decrypt_oauth(account: ClaudeAccount) -> Optional[dict[str, Any]]:
    """Decrypt and parse the stored OAuth block, if any."""
    if not account.oauth_encrypted:
        return None
    try:
        raw = encryption_service.decrypt(account.oauth_encrypted)
    except ValueError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _access_token_from_account(account: ClaudeAccount) -> Optional[str]:
    oauth = _decrypt_oauth(account)
    if not oauth:
        return None
    token = oauth.get("accessToken")
    return token if isinstance(token, str) and token.strip() else None


def _resolve_oauth_payload(
    oauth: Optional[dict[str, Any]],
    oauth_json: Optional[str],
    access_token: Optional[str],
) -> Optional[dict[str, Any]]:
    """
    Build an OAuth block from whichever create/update field was provided.

    Precedence: structured ``oauth`` dict (from login capture) > pasted ``oauth_json`` text
    > bare ``access_token`` paste.
    """
    if isinstance(oauth, dict) and oauth.get("accessToken"):
        return oauth
    if oauth_json and oauth_json.strip():
        try:
            parsed = json.loads(oauth_json)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="JSON OAuth invalide"
            ) from None
        block = parsed.get("claudeAiOauth") if isinstance(parsed, dict) else None
        block = block if isinstance(block, dict) else parsed
        if isinstance(block, dict) and block.get("accessToken"):
            return block
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON OAuth invalide — champ accessToken manquant",
        )
    if access_token and access_token.strip():
        return {"accessToken": access_token.strip()}
    return None


def _encrypt_oauth(oauth: dict[str, Any]) -> str:
    return encryption_service.encrypt(json.dumps(oauth))


async def _refresh_account(account: ClaudeAccount) -> None:
    """Probe Claude Max usage and update cache columns on ``account``."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    account.last_checked_at = now
    access_token = _access_token_from_account(account)
    if not access_token:
        account.last_error = "Ajoute un jeton OAuth pour lire les quotas"
        return

    reading = await fetch_claude_usage(access_token)
    if reading.error and reading.five_hour_utilization is None and reading.seven_day_utilization is None:
        account.last_error = reading.error
        return
    account.five_hour_utilization = reading.five_hour_utilization
    account.seven_day_utilization = reading.seven_day_utilization
    account.seven_day_opus_utilization = reading.seven_day_opus_utilization
    account.resets_at = reading.resets_at
    account.last_error = reading.error


async def _machine_usage(db: Session, user_id: int) -> Optional[MachineClaudeUsage]:
    """Ask an online agent for the local Claude session usage."""
    machines = (
        db.query(Machine)
        .filter(Machine.user_id == user_id)
        .order_by(Machine.last_seen_at.desc(), Machine.name.asc())
        .all()
    )
    online = next((m for m in machines if agent_hub.is_online(m.id)), None)
    if online is None:
        return MachineClaudeUsage(
            source="none",
            error="Aucune machine en ligne — ouvre l’app desktop pour l’usage local",
        )

    resp = await agent_hub.request_agent(online.id, {"type": "claude.usage"}, timeout=25.0)
    if not resp:
        return MachineClaudeUsage(
            source="none",
            error="L’agent n’a pas répondu à la lecture Claude",
        )

    email: Optional[str] = None
    raw_email = resp.get("email")
    if isinstance(raw_email, str) and "@" in raw_email.strip():
        email = raw_email.strip()

    buckets_raw = resp.get("buckets")
    if not isinstance(buckets_raw, list) or not buckets_raw:
        return MachineClaudeUsage(
            source="live",
            email=email,
            error=resp.get("auth_error")
            or "Pas de session Claude locale (connecte-toi via `claude auth login`)",
        )

    five_u: Optional[float] = None
    seven_u: Optional[float] = None
    opus_u: Optional[float] = None
    resets_at: Optional[datetime] = None
    buckets: list[dict] = []
    for entry in buckets_raw:
        if not isinstance(entry, dict):
            continue
        bucket = str(entry.get("bucket") or "")
        raw = entry.get("utilization")
        util: Optional[float] = None
        if isinstance(raw, (int, float)):
            util = float(raw)
            if util > 1.0:
                util = min(util / 100.0, 1.0)
            util = max(0.0, min(util, 1.0))
        if bucket == "five_hour":
            five_u = util
        elif bucket == "seven_day":
            seven_u = util
        elif bucket == "seven_day_opus":
            opus_u = util
        reset_raw = entry.get("resets_at")
        if isinstance(reset_raw, str) and reset_raw and resets_at is None:
            try:
                parsed = datetime.fromisoformat(reset_raw.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.replace(tzinfo=None)
                resets_at = parsed
            except ValueError:
                pass
        buckets.append(
            {
                "bucket": bucket,
                "utilization": util,
                "resets_at": reset_raw,
            }
        )

    return MachineClaudeUsage(
        five_hour_utilization=five_u,
        seven_day_utilization=seven_u,
        seven_day_opus_utilization=opus_u,
        resets_at=resets_at,
        email=email,
        source="live",
        buckets=buckets,
    )


def _norm_token(token: str) -> str:
    return (token or "").strip()


def _sync_live_machine_flags(
    accounts: list[ClaudeAccount],
    machine: Optional[MachineClaudeUsage],
    live_access_token: Optional[str] = None,
    live_oauth: Optional[dict[str, Any]] = None,
) -> Optional[ClaudeAccount]:
    """
    Mark the vault row that matches the live Claude session; clear others.

    Matching order: live email → live access token.
    Refreshes OAuth on the matched row when a live block is available.
    """
    machine_email = (machine.email or "").strip().lower() if machine else ""
    live = _norm_token(live_access_token or "")
    matched: Optional[ClaudeAccount] = None

    for account in accounts:
        is_live = False
        if machine_email and (account.email or "").strip().lower() == machine_email:
            is_live = True
        elif live:
            token = _access_token_from_account(account)
            if token and _norm_token(token) == live:
                is_live = True

        account.from_machine = is_live
        if is_live:
            matched = account
            if live_oauth:
                account.oauth_encrypted = _encrypt_oauth(live_oauth)

    return matched


def _machine_already_imported(
    accounts: list[ClaudeAccount],
    machine: Optional[MachineClaudeUsage],
    online_machine_name: Optional[str],
    live_access_token: Optional[str] = None,
) -> bool:
    """
    True when the pinned live Claude session is already in the vault.

    Matching order: live email → live access token.
    Does not treat a stale ``from_machine`` flag on another account as a match.
    """
    del online_machine_name  # kept for call-site compatibility
    if not accounts:
        return False

    machine_email = (machine.email or "").strip().lower() if machine else ""
    if machine_email:
        for account in accounts:
            if (account.email or "").strip().lower() == machine_email:
                return True

    live = _norm_token(live_access_token or "")
    if live:
        for account in accounts:
            token = _access_token_from_account(account)
            if token and _norm_token(token) == live:
                return True

    return False


async def _live_session_export(machine_id: int) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """
    Best-effort local Claude OAuth block from an online agent.

    Returns:
        ``(oauth_block, email)`` — either may be None.
    """
    resp = await agent_hub.request_agent(machine_id, {"type": "claude.session.export"}, timeout=12.0)
    if not resp:
        return None, None
    oauth = resp.get("oauth")
    oauth_out = oauth if isinstance(oauth, dict) and oauth.get("accessToken") else None
    email_out: Optional[str] = None
    raw_email = resp.get("email")
    if isinstance(raw_email, str) and "@" in raw_email.strip():
        email_out = raw_email.strip()
    if not email_out and oauth_out:
        email_out = email_from_oauth(oauth_out)
    return oauth_out, email_out


def _upsert_machine_vault_row(
    db: Session,
    user_id: int,
    *,
    oauth: dict[str, Any],
    email: Optional[str],
    machine_name: str,
) -> ClaudeAccount:
    """
    Create or update the vault row for the live machine session.

    Matches by email (or label fallback) only — never rewrites another account
    that still has a stale ``from_machine`` flag after a Claude login switch.
    """
    label = (email or f"Machine · {machine_name}")[:120]
    existing: Optional[ClaudeAccount] = None
    if email:
        existing = (
            db.query(ClaudeAccount)
            .filter(ClaudeAccount.user_id == user_id, ClaudeAccount.email == email)
            .first()
        )
    if existing is None and not email:
        existing = (
            db.query(ClaudeAccount)
            .filter(ClaudeAccount.user_id == user_id, ClaudeAccount.label == label)
            .first()
        )

    for other in db.query(ClaudeAccount).filter(ClaudeAccount.user_id == user_id).all():
        other.from_machine = False

    if existing:
        existing.oauth_encrypted = _encrypt_oauth(oauth)
        if email:
            existing.email = email
            existing.label = email[:120]
        existing.from_machine = True
        return existing

    account = ClaudeAccount(
        user_id=user_id,
        label=label,
        email=email,
        oauth_encrypted=_encrypt_oauth(oauth),
        from_machine=True,
    )
    db.add(account)
    return account


def _is_machine_mirror(account: ClaudeAccount, machine: Optional[MachineClaudeUsage]) -> bool:
    """
    True when this vault row is the live Claude session (visual hide only).

    Uses live email identity — a stale ``from_machine`` flag must not hide
    an account after the user switches Claude login.
    """
    machine_email = (machine.email or "").strip().lower() if machine else ""
    if not machine_email:
        return False
    return (account.email or "").strip().lower() == machine_email


def _vault_display_accounts(
    accounts: list[ClaudeAccount], machine: Optional[MachineClaudeUsage]
) -> list[ClaudeAccount]:
    """Vault rows shown in UI — hides only the live account (by email)."""
    return [a for a in accounts if not _is_machine_mirror(a, machine)]


async def _overview_for_user(
    db: Session,
    user_id: int,
    *,
    refresh_vault: bool = False,
) -> ClaudeAccountsOverview:
    """Build the Claude accounts page payload (shared by list + refresh)."""
    accounts = (
        db.query(ClaudeAccount)
        .filter(ClaudeAccount.user_id == user_id)
        .order_by(ClaudeAccount.created_at.asc())
        .all()
    )
    if refresh_vault:
        for account in accounts:
            if account.is_active:
                await _refresh_account(account)
        db.commit()
        for account in accounts:
            db.refresh(account)

    machines = (
        db.query(Machine)
        .filter(Machine.user_id == user_id)
        .order_by(Machine.last_seen_at.desc(), Machine.name.asc())
        .all()
    )
    online = next((m for m in machines if agent_hub.is_online(m.id)), None)
    machine = await _machine_usage(db, user_id)

    live_oauth: Optional[dict[str, Any]] = None
    live_email: Optional[str] = None
    if online is not None:
        live_oauth, live_email = await _live_session_export(online.id)
        if live_email and machine and not machine.email:
            machine.email = live_email

    live_token = live_oauth.get("accessToken") if isinstance(live_oauth, dict) else None
    imported = _machine_already_imported(
        accounts,
        machine,
        online.name if online else None,
        live_access_token=live_token,
    )

    # Auto-sync: pinned live session → vault, so « Importer machine » stays hidden.
    if online is not None and not imported and live_oauth:
        email = (machine.email if machine else None) or live_email
        _upsert_machine_vault_row(
            db,
            user_id,
            oauth=live_oauth,
            email=email,
            machine_name=online.name,
        )
        db.commit()
        accounts = (
            db.query(ClaudeAccount)
            .filter(ClaudeAccount.user_id == user_id)
            .order_by(ClaudeAccount.created_at.asc())
            .all()
        )
        imported = True
        live_row = _sync_live_machine_flags(
            accounts, machine, live_token, live_oauth=live_oauth
        )
        if live_row and live_row.oauth_encrypted:
            await _refresh_account(live_row)
        db.commit()
        for account in accounts:
            db.refresh(account)
    else:
        _sync_live_machine_flags(accounts, machine, live_token, live_oauth=live_oauth)
        db.commit()
        for account in accounts:
            db.refresh(account)

    pick = pick_best_claude_account(
        [
            (a.id, a.five_hour_utilization, a.seven_day_utilization)
            for a in accounts
            if a.is_active
        ]
    )
    display = _vault_display_accounts(accounts, machine)
    display_ids = {a.id for a in display}
    machine_ids = {a.id for a in accounts if _is_machine_mirror(a, machine)}
    machine_preferred = pick is not None and pick in machine_ids
    selected_vault_id = pick if pick in display_ids else None

    return ClaudeAccountsOverview(
        machine=machine,
        accounts=[_to_response(a) for a in display],
        selected_account_id=selected_vault_id,
        machine_imported=imported,
        machine_preferred=machine_preferred,
    )


@router.get("", response_model=ClaudeAccountsOverview)
async def list_claude_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """Overview for the Claude accounts page (pinned machine + vault)."""
    return await _overview_for_user(db, current_user.id, refresh_vault=False)


@router.post("", response_model=ClaudeAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_claude_account(
    payload: ClaudeAccountCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Add a Claude account to the vault (OAuth encrypted at rest).
    """
    oauth = _resolve_oauth_payload(payload.oauth, payload.oauth_json, payload.access_token)
    if not oauth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session OAuth requise — connecte-toi avec Claude ou colle un jeton",
        )

    email = (payload.email or "").strip() or None
    if not email:
        email = email_from_oauth(oauth)

    label = (payload.label or email or "Compte Claude").strip()[:120]

    account = ClaudeAccount(
        user_id=current_user.id,
        label=label,
        email=email,
        password_encrypted=(
            encryption_service.encrypt(payload.password) if payload.password else None
        ),
        oauth_encrypted=_encrypt_oauth(oauth),
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    await _refresh_account(account)
    db.commit()
    db.refresh(account)

    return _to_response(account)


@router.post("/refresh", response_model=ClaudeAccountsOverview)
async def refresh_all_usage(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Re-fetch Claude Max usage for every vaulted account + pinned machine session.
    """
    return await _overview_for_user(db, current_user.id, refresh_vault=True)


async def _require_online_agent(db: Session, user_id: int) -> Machine:
    """Return an online machine for the user or raise 503."""
    machines = (
        db.query(Machine)
        .filter(Machine.user_id == user_id)
        .order_by(Machine.last_seen_at.desc())
        .all()
    )
    online = next((m for m in machines if agent_hub.is_online(m.id)), None)
    if online is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Aucune machine en ligne — ouvre l’app desktop NightForge",
        )
    return online


@router.post("/login/start")
async def claude_login_start(
    payload: Optional[dict] = Body(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Start Claude account capture on an online agent (``claude auth login``).

    Pass ``keep_on_machine: true`` when connecting the machine itself (no prior
    session to restore) — e.g. after the user skipped Claude login at app start.
    """
    body = payload or {}
    keep_on_machine = bool(body.get("keep_on_machine"))
    online = await _require_online_agent(db, current_user.id)
    resp = await agent_hub.request_agent(
        online.id,
        {"type": "claude.login.start", "keep_on_machine": keep_on_machine},
        timeout=45.0,
    )
    if not resp:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="L’agent n’a pas répondu au démarrage du login Claude",
        )
    if resp.get("status") == "error" or not resp.get("login_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resp.get("error") or "Impossible de démarrer la capture Claude",
        )
    return {
        "login_id": resp.get("login_id"),
        "login_url": resp.get("login_url"),
        "status": resp.get("status") or "pending",
        "mode": resp.get("mode") or "cli",
        "keep_on_machine": resp.get("keep_on_machine", keep_on_machine),
        "note": resp.get("note"),
        "machine_id": online.id,
    }


@router.post("/login/poll")
async def claude_login_poll(
    payload: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """Poll whether the agent captured a new Claude OAuth block."""
    login_id = str((payload or {}).get("login_id") or "").strip()
    if not login_id:
        raise HTTPException(status_code=400, detail="login_id requis")
    online = await _require_online_agent(db, current_user.id)
    resp = await agent_hub.request_agent(
        online.id,
        {"type": "claude.login.poll", "login_id": login_id},
        timeout=12.0,
    )
    if not resp:
        raise HTTPException(
            status_code=504,
            detail="L’agent ne répond plus — vérifie que NightForge Desktop est ouvert",
        )
    return resp


@router.post("/login/complete")
async def claude_login_complete(
    payload: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """User confirmed login finished — capture OAuth block (machine session restored by the agent)."""
    login_id = str((payload or {}).get("login_id") or "").strip()
    if not login_id:
        raise HTTPException(status_code=400, detail="login_id requis")
    online = await _require_online_agent(db, current_user.id)
    resp = await agent_hub.request_agent(
        online.id,
        {"type": "claude.login.complete", "login_id": login_id},
        timeout=25.0,
    )
    if not resp:
        raise HTTPException(status_code=504, detail="Agent timeout")
    if resp.get("status") == "error":
        raise HTTPException(
            status_code=400, detail=resp.get("error") or "Connexion Claude non détectée"
        )
    return resp


@router.post("/login/cancel")
async def claude_login_cancel(
    payload: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """Cancel login and restore the previous machine Claude session."""
    login_id = str((payload or {}).get("login_id") or "").strip()
    if not login_id:
        return {"status": "ok"}
    online = await _require_online_agent(db, current_user.id)
    resp = await agent_hub.request_agent(
        online.id,
        {"type": "claude.login.cancel", "login_id": login_id},
        timeout=15.0,
    )
    return resp or {"status": "ok"}


@router.post("/import-machine", response_model=ClaudeAccountResponse, status_code=status.HTTP_201_CREATED)
async def import_machine_session(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Ask an online agent for the local Claude OAuth block and vault it.
    """
    online = await _require_online_agent(db, current_user.id)

    resp = await agent_hub.request_agent(online.id, {"type": "claude.session.export"}, timeout=25.0)
    if resp is None:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "L’agent n’a pas répondu à l’export de session — "
                "vérifie que NightForge Desktop est ouvert et réessaie."
            ),
        )

    oauth = resp.get("oauth")
    if not isinstance(oauth, dict) or not oauth.get("accessToken"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resp.get("error")
            if isinstance(resp.get("error"), str) and resp.get("error")
            else "Session Claude locale introuvable — connecte-toi via `claude auth login`",
        )

    email = resp.get("email") if isinstance(resp.get("email"), str) else email_from_oauth(oauth)
    account = _upsert_machine_vault_row(
        db,
        current_user.id,
        oauth=oauth,
        email=email,
        machine_name=online.name,
    )

    db.commit()
    db.refresh(account)
    await _refresh_account(account)
    db.commit()
    db.refresh(account)
    return _to_response(account)


@router.patch("/{account_id}", response_model=ClaudeAccountResponse)
async def update_claude_account(
    account_id: int,
    payload: ClaudeAccountUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """Update label / secrets / active flag for a vault account."""
    account = _get_owned(db, current_user.id, account_id)
    if payload.email is not None:
        email = payload.email.strip() or None
        account.email = email
        if email:
            account.label = email[:120]
    if payload.label is not None and payload.email is None:
        account.label = payload.label.strip()
    if payload.is_active is not None:
        account.is_active = payload.is_active

    if payload.clear_password:
        account.password_encrypted = None
    elif payload.password is not None:
        account.password_encrypted = (
            encryption_service.encrypt(payload.password) if payload.password else None
        )

    if payload.clear_oauth:
        account.oauth_encrypted = None
    else:
        oauth = _resolve_oauth_payload(payload.oauth, payload.oauth_json, payload.access_token)
        if oauth:
            account.oauth_encrypted = _encrypt_oauth(oauth)
            if not account.email:
                account.email = email_from_oauth(oauth)

    db.commit()
    db.refresh(account)
    return _to_response(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_claude_account(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a vaulted Claude account."""
    account = _get_owned(db, current_user.id, account_id)
    db.delete(account)
    db.commit()


@router.get("/{account_id}/credentials", response_model=ClaudeAccountCredentials)
async def reveal_credentials(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Decrypt email/password reminder for the account drawer.

    The OAuth block is never returned here.
    """
    account = _get_owned(db, current_user.id, account_id)
    password: Optional[str] = None
    if account.password_encrypted:
        try:
            password = encryption_service.decrypt(account.password_encrypted)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Déchiffrement impossible — vérifie ENCRYPTION_KEY",
            ) from exc
    return ClaudeAccountCredentials(
        id=account.id,
        label=account.label,
        email=account.email,
        password=password,
    )


@router.post("/{account_id}/refresh", response_model=ClaudeAccountResponse)
async def refresh_one(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """Refresh usage for a single vault account."""
    account = _get_owned(db, current_user.id, account_id)
    await _refresh_account(account)
    db.commit()
    db.refresh(account)
    return _to_response(account)
