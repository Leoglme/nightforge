"""
Cursor accounts vault — CRUD, credentials reveal, usage refresh, account pick.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from models.cursor_account import CursorAccount
from models.machine import Machine
from models.user import User
from schemas.cursor_account import (
    CursorAccountCreate,
    CursorAccountCredentials,
    CursorAccountResponse,
    CursorAccountUpdate,
    CursorAccountsOverview,
    MachineCursorUsage,
)
from services.agent_hub import agent_hub
from services.auth_service import get_current_active_user
from services.cursor_usage_service import (
    email_from_token,
    fetch_cursor_usage,
    pick_best_account,
)
from services.encryption_service import encryption_service

router = APIRouter(prefix="/cursor-accounts", tags=["cursor-accounts"])


def _avg(auto_u: Optional[float], api_u: Optional[float]) -> Optional[float]:
    values = [v for v in (auto_u, api_u) if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _to_response(account: CursorAccount) -> CursorAccountResponse:
    return CursorAccountResponse(
        id=account.id,
        label=account.label,
        email=account.email,
        has_password=bool(account.password_encrypted),
        has_session_token=bool(account.session_token_encrypted),
        has_api_key=bool(account.api_key_encrypted),
        auto_utilization=account.auto_utilization,
        api_utilization=account.api_utilization,
        average_utilization=_avg(account.auto_utilization, account.api_utilization),
        resets_at=account.resets_at,
        last_checked_at=account.last_checked_at,
        last_error=account.last_error,
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _get_owned(
    db: Session, user_id: int, account_id: int
) -> CursorAccount:
    account = (
        db.query(CursorAccount)
        .filter(CursorAccount.id == account_id, CursorAccount.user_id == user_id)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    return account


async def _refresh_account(account: CursorAccount) -> None:
    """Probe Cursor usage and update cache columns on ``account``."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    account.last_checked_at = now
    if not account.session_token_encrypted:
        account.last_error = "Ajoute un token de session pour lire les quotas"
        return
    try:
        token = encryption_service.decrypt(account.session_token_encrypted)
    except ValueError:
        account.last_error = "Impossible de déchiffrer le token (ENCRYPTION_KEY ?)"
        return

    reading = await fetch_cursor_usage(token)
    if reading.email and not account.email:
        account.email = reading.email
    if reading.error and reading.auto_utilization is None and reading.api_utilization is None:
        account.last_error = reading.error
        return
    account.auto_utilization = reading.auto_utilization
    account.api_utilization = reading.api_utilization
    account.resets_at = reading.resets_at
    account.last_error = reading.error


async def _machine_usage(db: Session, user_id: int) -> Optional[MachineCursorUsage]:
    """Ask an online agent for the local Cursor session usage."""
    machines = (
        db.query(Machine)
        .filter(Machine.user_id == user_id)
        .order_by(Machine.last_seen_at.desc(), Machine.name.asc())
        .all()
    )
    online = next((m for m in machines if agent_hub.is_online(m.id)), None)
    if online is None:
        return MachineCursorUsage(
            source="none",
            error="Aucune machine en ligne — ouvre l’app desktop pour l’usage local",
        )

    cursor_resp = await agent_hub.request_agent(
        online.id, {"type": "cursor.usage"}, timeout=25.0
    )
    if not cursor_resp:
        return MachineCursorUsage(
            source="none",
            error="L’agent n’a pas répondu à la lecture Cursor",
        )

    email: Optional[str] = None
    raw_email = cursor_resp.get("email")
    if isinstance(raw_email, str) and "@" in raw_email.strip():
        email = raw_email.strip()

    # Fallback: dedicated session export often has cachedEmail even when JWT does not.
    if not email:
        export_resp = await agent_hub.request_agent(
            online.id, {"type": "cursor.session.export"}, timeout=15.0
        )
        if export_resp and isinstance(export_resp.get("email"), str):
            candidate = export_resp["email"].strip()
            if "@" in candidate:
                email = candidate

    buckets_raw = cursor_resp.get("buckets")
    if not isinstance(buckets_raw, list) or not buckets_raw:
        return MachineCursorUsage(
            source="live",
            email=email,
            error=cursor_resp.get("error")
            or "Pas de session Cursor locale (connecte-toi dans Cursor IDE)",
        )

    auto_u: Optional[float] = None
    api_u: Optional[float] = None
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
        if bucket == "cursor_auto":
            auto_u = util
        elif bucket == "cursor_api":
            api_u = util
        reset_raw = entry.get("resets_at")
        if isinstance(reset_raw, str) and reset_raw:
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
                "label": entry.get("label"),
                "utilization": util,
                "resets_at": reset_raw,
            }
        )

    return MachineCursorUsage(
        auto_utilization=auto_u,
        api_utilization=api_u,
        average_utilization=_avg(auto_u, api_u),
        resets_at=resets_at,
        email=email,
        source="live",
        buckets=buckets,
    )


def _norm_token(token: str) -> str:
    """Normalize Workos / JWT session token for equality checks."""
    return (token or "").strip().replace("%3A%3A", "::")


def _machine_already_imported(
    accounts: list[CursorAccount],
    machine: Optional[MachineCursorUsage],
    online_machine_name: Optional[str],
    live_session_token: Optional[str] = None,
) -> bool:
    """
    True when the pinned machine session is already in the vault.

    Matching order: explicit ``from_machine`` flag → email → label → live token.
    Side effect: sets ``from_machine`` on the matching row when found.
    """
    if not accounts:
        return False

    for account in accounts:
        if bool(getattr(account, "from_machine", False)):
            return True

    machine_email = (machine.email or "").strip().lower() if machine else ""
    if machine_email:
        for account in accounts:
            if (account.email or "").strip().lower() == machine_email:
                account.from_machine = True
                return True

    for account in accounts:
        label = (account.label or "").strip().lower()
        if label.startswith("machine ·") or label.startswith("machine:"):
            account.from_machine = True
            return True

    if online_machine_name:
        needle = online_machine_name.strip().lower()
        for account in accounts:
            label = (account.label or "").strip().lower()
            if needle and needle in label and "machine" in label:
                account.from_machine = True
                return True

    live = _norm_token(live_session_token or "")
    if live:
        for account in accounts:
            if not account.session_token_encrypted:
                continue
            try:
                stored = encryption_service.decrypt(account.session_token_encrypted)
            except Exception:  # noqa: BLE001
                continue
            if _norm_token(stored) == live:
                account.from_machine = True
                return True

    return False


async def _live_session_export(machine_id: int) -> tuple[Optional[str], Optional[str]]:
    """
    Best-effort local Cursor session from an online agent.

    Returns:
        ``(session_token, email)`` — either may be None.
    """
    resp = await agent_hub.request_agent(
        machine_id, {"type": "cursor.session.export"}, timeout=12.0
    )
    if not resp:
        return None, None
    token = resp.get("session_token")
    token_out = token.strip() if isinstance(token, str) and token.strip() else None
    email_out: Optional[str] = None
    raw_email = resp.get("email")
    if isinstance(raw_email, str) and "@" in raw_email.strip():
        email_out = raw_email.strip()
    if not email_out and token_out:
        email_out = email_from_token(token_out)
    return token_out, email_out


def _upsert_machine_vault_row(
    db: Session,
    user_id: int,
    *,
    token: str,
    email: Optional[str],
    machine_name: str,
) -> CursorAccount:
    """Create or update the vault row that mirrors the live machine session."""
    label = (email or f"Machine · {machine_name}")[:120]
    existing: Optional[CursorAccount] = None
    if email:
        existing = (
            db.query(CursorAccount)
            .filter(CursorAccount.user_id == user_id, CursorAccount.email == email)
            .first()
        )
    if existing is None:
        existing = (
            db.query(CursorAccount)
            .filter(
                CursorAccount.user_id == user_id,
                CursorAccount.from_machine.is_(True),
            )
            .first()
        )
    if existing is None:
        existing = (
            db.query(CursorAccount)
            .filter(CursorAccount.user_id == user_id, CursorAccount.label == label)
            .first()
        )

    if existing:
        existing.session_token_encrypted = encryption_service.encrypt(token)
        if email:
            existing.email = email
            existing.label = email[:120]
        existing.from_machine = True
        return existing

    account = CursorAccount(
        user_id=user_id,
        label=label,
        email=email,
        session_token_encrypted=encryption_service.encrypt(token),
        from_machine=True,
    )
    db.add(account)
    return account


def _is_machine_mirror(
    account: CursorAccount,
    machine: Optional[MachineCursorUsage],
) -> bool:
    """True when this vault row is the same identity as the pinned machine session."""
    if bool(getattr(account, "from_machine", False)):
        return True
    machine_email = (machine.email or "").strip().lower() if machine else ""
    if machine_email and (account.email or "").strip().lower() == machine_email:
        return True
    return False


def _vault_display_accounts(
    accounts: list[CursorAccount],
    machine: Optional[MachineCursorUsage],
) -> list[CursorAccount]:
    """Vault rows shown in UI — excludes the pinned machine mirror."""
    return [a for a in accounts if not _is_machine_mirror(a, machine)]


async def _overview_for_user(
    db: Session,
    user_id: int,
    *,
    refresh_vault: bool = False,
) -> CursorAccountsOverview:
    """Build the Cursor accounts page payload (shared by list + refresh)."""
    accounts = (
        db.query(CursorAccount)
        .filter(CursorAccount.user_id == user_id)
        .order_by(CursorAccount.created_at.asc())
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

    live_token: Optional[str] = None
    live_email: Optional[str] = None
    if online is not None:
        live_token, live_email = await _live_session_export(online.id)
        if live_email and machine and not machine.email:
            machine.email = live_email

    imported = _machine_already_imported(
        accounts,
        machine,
        online.name if online else None,
        live_session_token=live_token,
    )

    # Auto-sync: pinned live session → vault, so « Importer machine » stays hidden.
    if online is not None and not imported and live_token:
        email = (machine.email if machine else None) or live_email
        _upsert_machine_vault_row(
            db,
            user_id,
            token=live_token,
            email=email,
            machine_name=online.name,
        )
        db.commit()
        accounts = (
            db.query(CursorAccount)
            .filter(CursorAccount.user_id == user_id)
            .order_by(CursorAccount.created_at.asc())
            .all()
        )
        imported = True
        # Best-effort usage fill for the new/updated row.
        for account in accounts:
            if account.from_machine and account.session_token_encrypted:
                await _refresh_account(account)
                break
        db.commit()
        for account in accounts:
            db.refresh(account)
    elif imported:
        db.commit()

    pick = pick_best_account(
        [(a.id, a.auto_utilization, a.api_utilization) for a in accounts if a.is_active]
    )
    display = _vault_display_accounts(accounts, machine)
    display_ids = {a.id for a in display}
    machine_ids = {a.id for a in accounts if _is_machine_mirror(a, machine)}
    machine_preferred = pick is not None and pick in machine_ids
    selected_vault_id = pick if pick in display_ids else None

    return CursorAccountsOverview(
        machine=machine,
        accounts=[_to_response(a) for a in display],
        selected_account_id=selected_vault_id,
        machine_imported=imported,
        machine_preferred=machine_preferred,
    )


@router.get("", response_model=CursorAccountsOverview)
async def list_cursor_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """Overview for the Cursor accounts page (pinned machine + vault)."""
    return await _overview_for_user(db, current_user.id, refresh_vault=False)


@router.post("", response_model=CursorAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_cursor_account(
    payload: CursorAccountCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Add a Cursor account to the vault (secrets encrypted at rest).
    """
    email = (payload.email or "").strip()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email requis",
        )
    token = (payload.session_token or "").strip() or None
    if token and "@" not in email:
        inferred = email_from_token(token)
        if inferred:
            email = inferred

    label = (payload.label or email).strip()[:120]

    account = CursorAccount(
        user_id=current_user.id,
        label=label,
        email=email,
        password_encrypted=(
            encryption_service.encrypt(payload.password) if payload.password else None
        ),
        session_token_encrypted=(
            encryption_service.encrypt(token) if token else None
        ),
        api_key_encrypted=(
            encryption_service.encrypt(payload.api_key.strip())
            if payload.api_key and payload.api_key.strip()
            else None
        ),
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    if account.session_token_encrypted:
        await _refresh_account(account)
        db.commit()
        db.refresh(account)

    return _to_response(account)


@router.post("/refresh", response_model=CursorAccountsOverview)
async def refresh_all_usage(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Re-fetch plan usage for every vaulted account + pinned machine session.
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
async def cursor_login_start(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Start Cursor account capture on an online agent (NoDriver browser login).
    """
    online = await _require_online_agent(db, current_user.id)
    resp = await agent_hub.request_agent(
        online.id, {"type": "cursor.login.start"}, timeout=45.0
    )
    if not resp:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="L’agent n’a pas répondu au démarrage du login Cursor",
        )
    if resp.get("status") == "error" or not resp.get("login_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resp.get("error")
            or resp.get("warning")
            or "Impossible de démarrer la capture Cursor (NoDriver)",
        )
    return {
        "login_id": resp.get("login_id"),
        "login_url": resp.get("login_url"),
        "status": resp.get("status") or "pending",
        "mode": resp.get("mode") or "browser",
        "note": resp.get("note"),
        "warning": resp.get("warning"),
        "session_token": resp.get("session_token"),
        "email": resp.get("email"),
        "machine_id": online.id,
    }


@router.post("/login/poll")
async def cursor_login_poll(
    payload: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """Poll whether NoDriver captured a Cursor session cookie."""
    login_id = str((payload or {}).get("login_id") or "").strip()
    if not login_id:
        raise HTTPException(status_code=400, detail="login_id requis")
    online = await _require_online_agent(db, current_user.id)
    resp = await agent_hub.request_agent(
        online.id,
        {"type": "cursor.login.poll", "login_id": login_id},
        timeout=12.0,
    )
    if not resp:
        raise HTTPException(
            status_code=504,
            detail="L’agent ne répond plus — vérifie que NightForge Desktop est ouvert",
        )
    return resp


@router.post("/login/complete")
async def cursor_login_complete(
    payload: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """User confirmed login finished — capture session token (and restore machine auth)."""
    login_id = str((payload or {}).get("login_id") or "").strip()
    if not login_id:
        raise HTTPException(status_code=400, detail="login_id requis")
    online = await _require_online_agent(db, current_user.id)
    resp = await agent_hub.request_agent(
        online.id,
        {"type": "cursor.login.complete", "login_id": login_id},
        timeout=25.0,
    )
    if not resp:
        raise HTTPException(status_code=504, detail="Agent timeout")
    if resp.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=resp.get("error") or "Connexion Cursor non détectée",
        )
    return resp


@router.post("/login/cancel")
async def cursor_login_cancel(
    payload: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """Cancel login and restore the previous machine Cursor session."""
    login_id = str((payload or {}).get("login_id") or "").strip()
    if not login_id:
        return {"status": "ok"}
    online = await _require_online_agent(db, current_user.id)
    resp = await agent_hub.request_agent(
        online.id,
        {"type": "cursor.login.cancel", "login_id": login_id},
        timeout=15.0,
    )
    return resp or {"status": "ok"}


@router.post("/import-machine", response_model=CursorAccountResponse, status_code=status.HTTP_201_CREATED)
async def import_machine_session(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Ask an online agent for the local Cursor session token and vault it.
    """
    online = await _require_online_agent(db, current_user.id)

    resp = await agent_hub.request_agent(
        online.id, {"type": "cursor.session.export"}, timeout=20.0
    )
    if not resp or not resp.get("session_token"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resp.get("error")
            if isinstance(resp, dict) and resp.get("error")
            else "Session Cursor locale introuvable — connecte-toi dans Cursor IDE",
        )

    token = str(resp["session_token"]).strip()
    email = resp.get("email") if isinstance(resp.get("email"), str) else email_from_token(token)
    label = (email or f"Machine · {online.name}")[:120]

    existing = None
    if email:
        existing = (
            db.query(CursorAccount)
            .filter(
                CursorAccount.user_id == current_user.id,
                CursorAccount.email == email,
            )
            .first()
        )
    if existing is None:
        existing = (
            db.query(CursorAccount)
            .filter(
                CursorAccount.user_id == current_user.id,
                CursorAccount.label == label,
            )
            .first()
        )
    if existing:
        existing.session_token_encrypted = encryption_service.encrypt(token)
        if email:
            existing.email = email
        existing.from_machine = True
        account = existing
    else:
        account = CursorAccount(
            user_id=current_user.id,
            label=label,
            email=email,
            session_token_encrypted=encryption_service.encrypt(token),
            from_machine=True,
        )
        db.add(account)

    db.commit()
    db.refresh(account)
    await _refresh_account(account)
    db.commit()
    db.refresh(account)
    return _to_response(account)


@router.patch("/{account_id}", response_model=CursorAccountResponse)
async def update_cursor_account(
    account_id: int,
    payload: CursorAccountUpdate,
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

    if payload.clear_session_token:
        account.session_token_encrypted = None
    elif payload.session_token is not None:
        token = payload.session_token.strip()
        account.session_token_encrypted = (
            encryption_service.encrypt(token) if token else None
        )
        if token and not account.email:
            account.email = email_from_token(token)

    if payload.clear_api_key:
        account.api_key_encrypted = None
    elif payload.api_key is not None:
        key = payload.api_key.strip()
        account.api_key_encrypted = encryption_service.encrypt(key) if key else None

    db.commit()
    db.refresh(account)
    return _to_response(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cursor_account(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a vaulted Cursor account."""
    account = _get_owned(db, current_user.id, account_id)
    db.delete(account)
    db.commit()


@router.get("/{account_id}/credentials", response_model=CursorAccountCredentials)
async def reveal_credentials(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Decrypt email/password reminder for the account drawer.

    Session token and API key are never returned here.
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
    return CursorAccountCredentials(
        id=account.id,
        label=account.label,
        email=account.email,
        password=password,
    )


@router.post("/{account_id}/refresh", response_model=CursorAccountResponse)
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
