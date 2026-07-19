"""
Ideas expander — turn free-form keywords into queue-ready prompts.

Order: online agent (Cursor/Claude) → Groq cloud LLM → local heuristic.
Planning rules are adapted from the NightForge ``plan-de-session`` skill.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional, Tuple

import httpx

from core.config import settings
from schemas.ideas import ExpandedIdeaDraft

logger = logging.getLogger(__name__)

# Keywords → (provider, model, effort) — mirrors plan-de-session + NightForge providers.
_AESTHETIC = re.compile(
    r"\b(beau|esth|design|animat|fluide|visuel|style|polish|ressenti|"
    r"harmonie|look|couleur|palette|drawer|satisfaisant|agréable)\b",
    re.IGNORECASE,
)
_MOCKUP = re.compile(
    r"\b(maquette|pixel.?perfect|à l['']identique|comme la maquette|figma|pencil)\b",
    re.IGNORECASE,
)
_COMPLEX = re.compile(
    r"\b(archi|refacto|refactor|review|complex|raisonn|opuss?|profond|algo|"
    r"multi.?fichier|migration)\b",
    re.IGNORECASE,
)
_LOGIC = re.compile(
    r"\b(logique|comportement|état|state|hover|timing|délai|delay|conditionnel|"
    r"interaction|bug|fix)\b",
    re.IGNORECASE,
)
_MECHANICAL = re.compile(
    r"\b(typo|label|renomm|déplac|deplac|retir|ajout|texte|seo|meta|"
    r"posthog|contenu|copie|copier|rename|move|delete|add|sitemap|json.?ld)\b",
    re.IGNORECASE,
)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")

# Condensed plan-de-session for NightForge (Cursor + Claude). Same text for agent & Groq.
PLAN_SYSTEM = """Tu es le skill « plan-de-session » de NightForge.
Tu NE codes PAS. Tu découpes des idées en prompts prêts pour une file d'attente.

Objectif : minimiser la conso de tokens / quota, tout en choisissant le MEILLEUR
modèle disponible (Cursor OU Claude) pour chaque bloc — pas le plus cher par défaut,
pas non plus Composer partout.

## Principe
Découpe par NATURE de tâche (pas par page). Une même page peut donner plusieurs
sessions. Ne mélange JAMAIS esthétique Fable et logique / mécanique dans le même prompt.

## Classification → provider / model / effort

| Catégorie | Signaux | provider | model | effort | fast_mode |
|-----------|---------|----------|-------|--------|-----------|
| Mécanique / structurel / contenu / SEO / setup / PostHog | label, déplacer, typo, meta, pages légales | cursor | composer-2.5 | null | false |
| Logique / comportement simple | hover, état, bug d'interaction, timing | cursor | composer-2.5 | null | false |
| Logique tordue / raisonnement | état complexe, multi-fichiers subtil | claude | sonnet | high | false |
| Matcher une maquette | « comme la maquette », pixel-perfect | claude | sonnet | medium | false |
| Esthétique / ressenti / polish UI lourd | plus beau, fluide, harmonie, drawer, animation | claude | fable | xhigh | false |
| Visuel transverse | palette, style bouton global | claude | fable | xhigh | false |
| Archi / review profonde | refacto large, archi, raisonnement dur | claude | opus | high | false |
| Raisonnement Cursor (si tu préfères rester Cursor) | review légère | cursor | grok-4.5 | high | false |

Règle d'or Sonnet vs Fable : goût / ressenti visuel → Fable ; le reste → Sonnet ou Composer.
Règle d'or Cursor vs Claude : Composer pour le pas cher / mécanique ; Claude (sonnet/fable/opus)
quand la qualité ou le goût compte vraiment. Ne mets pas Fable sur Cursor sauf si tu as une
raison forte — préfère provider=claude, model=fable.

## Regroupement
- Un bloc cohérent (même composant / même sujet) = une session.
- Regroupe plusieurs petites corrections mécaniques du MÊME fichier si le contexte reste petit.
- Sessions Fable courtes. Ne mets pas 8 corrections d'une grosse page dans un seul prompt.
- Ordonne : visuel transverse → corrections composants → pages dépendantes → non-visuel (SEO…).

## Format de chaque prompt
- Commence par `Contexte :` (projet + fichiers @mention placeholders si chemins inconnus).
- Liste numérotée claire, sans inventer de comportement.
- Précise le périmètre (« ne touche pas au style » / « uniquement l'animation »).
- Sur un bloc Fable esthétique lourd, ajoute une ligne : « active le skill ui-ux-pro-max si dispo ».

## Sortie
Réponds UNIQUEMENT avec un JSON valide (pas de markdown, pas de fences) :
{
  "summary": "N sessions — … (répartition Cursor/Claude)",
  "items": [
    {
      "title": "titre court",
      "prompt": "prompt complet prêt à coller",
      "provider": "cursor" | "claude",
      "model": "composer-2.5" | "grok-4.5" | "sonnet" | "opus" | "fable" | "haiku",
      "effort": "low" | "medium" | "high" | "xhigh" | "max" | null,
      "fast_mode": false
    }
  ]
}
"""


def build_agent_prompt(*, ideas: str, project_name: str) -> str:
    """
    Build the planning prompt sent to Cursor / Claude on the agent (or Groq).

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
    if _MOCKUP.search(chunk) and not _AESTHETIC.search(chunk):
        return "claude", "sonnet", "medium", False
    if _AESTHETIC.search(chunk):
        return "claude", "fable", "xhigh", False
    if _COMPLEX.search(chunk):
        return "claude", "opus", "high", False
    if _LOGIC.search(chunk):
        return "cursor", "composer-2.5", None, False
    if _MECHANICAL.search(chunk):
        return "cursor", "composer-2.5", None, False
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
    Expand ideas without an LLM (offline / agent and Groq unavailable).

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


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """
    Best-effort extract of a JSON object from model output.

    Args:
        text: Raw model text.

    Returns:
        Parsed dict, or None.
    """
    if not text:
        return None

    candidates: List[str] = []
    fence = _JSON_FENCE.search(text)
    if fence:
        candidates.append(fence.group(1))
    match = _JSON_OBJECT.search(text)
    if match:
        candidates.append(match.group(0))

    for raw in candidates:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data
    return None


def drafts_from_agent_payload(payload: dict[str, Any]) -> Tuple[Optional[str], List[ExpandedIdeaDraft]]:
    """
    Parse an agent / Groq JSON payload into drafts.

    Args:
        payload: Response dict with optional summary + items.

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


async def expand_via_groq(
    *, ideas: str, project_name: str
) -> Tuple[Optional[str], List[ExpandedIdeaDraft], Optional[str]]:
    """
    Expand ideas via Groq Chat Completions (cloud fallback when agent is offline).

    Args:
        ideas: Raw user ideas.
        project_name: Target project name.

    Returns:
        (summary, drafts, model_id) — empty drafts if Groq unavailable or parse failed.
    """
    api_key = (settings.groq_api_key or "").strip()
    if not api_key:
        return None, [], None

    model = (settings.groq_model or "llama-3.3-70b-versatile").strip()
    user_prompt = build_agent_prompt(ideas=ideas, project_name=project_name)

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Tu planifies des prompts pour une file NightForge. "
                                "Réponds uniquement en JSON valide selon le schéma demandé."
                            ),
                        },
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
        response.raise_for_status()
        body = response.json()
        content = (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not isinstance(content, str):
            content = str(content or "")
    except Exception as exc:  # noqa: BLE001 — soft fallback to heuristic
        logger.warning("Groq ideas.expand failed: %s", exc)
        return None, [], None

    parsed = _extract_json_object(content)
    if not parsed:
        logger.warning("Groq ideas.expand: could not parse JSON from response")
        return None, [], None

    summary, drafts = drafts_from_agent_payload(parsed)
    return summary, drafts, model
