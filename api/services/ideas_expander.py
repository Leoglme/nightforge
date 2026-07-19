"""
Ideas expander — turn free-form keywords into queue-ready prompts.

Primary path: ask an online agent (Cursor Composer 2.5 preferred, Claude Haiku fallback).
Fallback: heuristic split + model heuristics inspired by the ``plan-de-session`` skill.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from schemas.ideas import ExpandedIdeaDraft

# Keywords → (provider, model, effort) — mirrors plan-de-session + Cursor preference.
_AESTHETIC = re.compile(
    r"\b(beau|esth|design|animat|fluide|visuel|style|polish|ui\b|ux\b|drawer|ressenti|"
    r"harmonie|maquette|look|couleur|palette)\b",
    re.IGNORECASE,
)
_COMPLEX = re.compile(
    r"\b(archi|refacto|refactor|review|complex|raisonn|opuss?|profond|algo)\b",
    re.IGNORECASE,
)
_MECHANICAL = re.compile(
    r"\b(fix|bug|typo|label|renomm|déplac|deplac|retir|ajout|texte|seo|meta|"
    r"posthog|contenu|copie|copier|rename|move|delete|add)\b",
    re.IGNORECASE,
)

PLAN_SYSTEM = """Tu es le skill « plan-de-session » de NightForge.
Tu NE codes PAS. Tu découpes des idées en prompts prêts pour une file d'attente.

Objectif : minimiser la conso de tokens / quota.

Règles de modèle (préférer le moins cher qui convient) :
- Tâche mécanique / fix / contenu / SEO / setup → provider=cursor, model=composer-2.5, effort=null, fast_mode=false
- Logique / comportement / review légère → provider=cursor, model=composer-2.5 (ou claude/sonnet si raisonnement requis), effort=medium|high
- Esthétique / ressenti / polish UI lourd → provider=claude, model=fable, effort=xhigh
- Archi profonde / raisonnement dur → provider=claude, model=opus, effort=high
- Entre Sonnet et Fable : ressenti visuel → Fable ; le reste → Sonnet ou Composer

Découpe par NATURE de tâche (pas par page). Ne mélange jamais esthétique Fable et logique Sonnet.

Réponds UNIQUEMENT avec un JSON valide (pas de markdown) :
{
  "summary": "N sessions — …",
  "items": [
    {
      "title": "titre court",
      "prompt": "prompt complet prêt à coller (Contexte + points numérotés)",
      "provider": "cursor" | "claude",
      "model": "composer-2.5" | "sonnet" | "opus" | "fable" | "haiku" | "grok-4.5",
      "effort": "low" | "medium" | "high" | "xhigh" | "max" | null,
      "fast_mode": false
    }
  ]
}
"""


def build_agent_prompt(*, ideas: str, project_name: str) -> str:
    """
    Build the planning prompt sent to Cursor / Claude on the agent.

    Args:
        ideas: Raw user ideas / keywords.
        project_name: Target project display name.

    Returns:
        Full prompt text.
    """
    return (
        f"{PLAN_SYSTEM}\n\n"
        f"Projet cible : {project_name}\n\n"
        f"Idées / mots-clés de l'utilisateur :\n{ideas.strip()}\n"
    )


def split_idea_chunks(ideas: str) -> List[str]:
    """
    Split a free-form blob into individual idea lines.

    Args:
        ideas: Raw text.

    Returns:
        Non-empty idea chunks.
    """
    text = ideas.replace("\r\n", "\n").strip()
    if not text:
        return []

    # Prefer bullet / numbered lists when present.
    bullet_lines = re.findall(
        r"(?:^|\n)\s*(?:[-*•]|\d+[.)])\s+(.+?)(?=(?:\n\s*(?:[-*•]|\d+[.)])\s+)|\Z)",
        text,
        flags=re.DOTALL,
    )
    if len(bullet_lines) >= 2:
        return [chunk.strip() for chunk in bullet_lines if chunk.strip()]

    parts = [p.strip() for p in re.split(r"\n{2,}|\n", text) if p.strip()]
    return parts if parts else [text]


def _classify(chunk: str) -> Tuple[str, str, Optional[str], bool]:
    """
    Heuristic provider/model/effort for one idea chunk.

    Returns:
        (provider, model, effort, fast_mode)
    """
    if _AESTHETIC.search(chunk):
        return "claude", "fable", "xhigh", False
    if _COMPLEX.search(chunk):
        return "claude", "opus", "high", False
    if _MECHANICAL.search(chunk):
        return "cursor", "composer-2.5", None, False
    # Default: cheapest Cursor model
    return "cursor", "composer-2.5", None, False


def _title_from_chunk(chunk: str) -> str:
    first = chunk.strip().split("\n", 1)[0].strip()
    first = re.sub(r"^[-*•]\s+", "", first)
    first = re.sub(r"^\d+[.)]\s+", "", first)
    return first[:80] if first else "Idée"


def _prompt_from_chunk(chunk: str, project_name: str) -> str:
    title = _title_from_chunk(chunk)
    body = chunk.strip()
    return (
        f"Contexte : projet « {project_name} ».\n"
        f"Objectif : {title}\n\n"
        f"Détails / mots-clés fournis :\n{body}\n\n"
        "Instructions :\n"
        "1. Lis le contexte du dépôt avant de modifier.\n"
        "2. Implémente uniquement ce qui est demandé, sans élargir le périmètre.\n"
        "3. Garde le style et l'architecture existants.\n"
        "4. Vérifie le résultat (lint / rendu) si pertinent."
    )


def heuristic_expand(*, ideas: str, project_name: str) -> Tuple[str, List[ExpandedIdeaDraft]]:
    """
    Expand ideas without an LLM (offline / agent unavailable).

    Args:
        ideas: Raw text.
        project_name: Project name for prompt context.

    Returns:
        (summary, drafts)
    """
    chunks = split_idea_chunks(ideas)
    drafts: List[ExpandedIdeaDraft] = []
    for chunk in chunks:
        provider, model, effort, fast_mode = _classify(chunk)
        drafts.append(
            ExpandedIdeaDraft(
                title=_title_from_chunk(chunk),
                prompt=_prompt_from_chunk(chunk, project_name),
                provider=provider,
                model=model,
                effort=effort,
                fast_mode=fast_mode,
            )
        )
    cursor_n = sum(1 for d in drafts if d.provider == "cursor")
    claude_n = len(drafts) - cursor_n
    summary = f"{len(drafts)} prompt(s) — {cursor_n} Cursor, {claude_n} Claude (heuristique)"
    return summary, drafts


def drafts_from_agent_payload(payload: dict[str, Any]) -> Tuple[Optional[str], List[ExpandedIdeaDraft]]:
    """
    Parse an agent ``ideas.expand.response`` payload into drafts.

    Args:
        payload: Agent JSON response.

    Returns:
        (summary, drafts)
    """
    summary = payload.get("summary")
    if summary is not None:
        summary = str(summary)

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return summary, []

    drafts: List[ExpandedIdeaDraft] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        prompt = entry.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            continue
        title = entry.get("title")
        drafts.append(
            ExpandedIdeaDraft(
                title=str(title)[:120] if title else None,
                prompt=prompt.strip(),
                provider=str(entry.get("provider") or "cursor")[:20],
                model=str(entry.get("model") or "composer-2.5")[:64],
                effort=(
                    str(entry["effort"])[:16]
                    if entry.get("effort") not in (None, "", "null")
                    else None
                ),
                fast_mode=bool(entry.get("fast_mode", False)),
            )
        )
    return summary, drafts
