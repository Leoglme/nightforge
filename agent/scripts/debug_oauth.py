"""One-off OAuth usage debug script."""
import asyncio
import json

import httpx

from nightforge_agent.quota_reader import (
    CLAUDE_USER_AGENT,
    OAUTH_BETA_HEADER,
    OAUTH_USAGE_URL,
    _load_oauth_block,
    _parse_five_hour_bucket,
    _refresh_oauth_token,
    _token_expired,
)


async def main() -> None:
    oauth = _load_oauth_block()
    print("oauth block:", bool(oauth))
    if not oauth:
        return
    print("expired:", _token_expired(oauth))
    print("has refreshToken:", bool(oauth.get("refreshToken")))
    access = oauth["accessToken"]
    headers = {
        "Authorization": f"Bearer {access}",
        "anthropic-beta": OAUTH_BETA_HEADER,
        "User-Agent": CLAUDE_USER_AGENT,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(OAUTH_USAGE_URL, headers=headers)
    print("usage without refresh status:", resp.status_code)
    print("body:", resp.text[:1200])
    if resp.status_code == 200:
        data = resp.json()
        print("parsed:", _parse_five_hour_bucket(data))
        print("keys:", list(data.keys()) if isinstance(data, dict) else type(data))
        return
    if _token_expired(oauth):
        oauth = await _refresh_oauth_token(oauth)
        print("refreshed:", bool(oauth))
    if not oauth:
        return
    access = oauth["accessToken"]
    headers["Authorization"] = f"Bearer {access}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(OAUTH_USAGE_URL, headers=headers)
    print("usage after refresh status:", resp.status_code)
    print("body:", resp.text[:1200])


if __name__ == "__main__":
    asyncio.run(main())
