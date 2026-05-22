from __future__ import annotations

import base64
from typing import Any

from utils.http_client import HttpClient

SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"


def _read_u32_le(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _parse_spl_mint_account(raw_data: bytes) -> dict[str, Any]:
    """
    SPL Token Mint layout size is usually 82 bytes.

    Layout:
    mintAuthorityOption: u32
    mintAuthority: pubkey 32
    supply: u64
    decimals: u8
    isInitialized: bool/u8
    freezeAuthorityOption: u32
    freezeAuthority: pubkey 32
    """
    if len(raw_data) < 82:
        return {
            "ok": False,
            "error": f"Mint account data too short: {len(raw_data)} bytes",
        }

    mint_authority_option = _read_u32_le(raw_data, 0)
    decimals = raw_data[44]
    is_initialized = raw_data[45] == 1
    freeze_authority_option = _read_u32_le(raw_data, 46)

    mint_authority_revoked = mint_authority_option == 0
    freeze_authority_disabled = freeze_authority_option == 0

    return {
        "ok": True,
        "mint_authority_revoked": mint_authority_revoked,
        "freeze_authority_disabled": freeze_authority_disabled,
        "is_initialized": is_initialized,
        "decimals": decimals,
    }


def fetch_mint_account(http: HttpClient, mint_address: str) -> bytes | None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            mint_address,
            {
                "encoding": "base64",
                "commitment": "confirmed",
            },
        ],
    }

    response = http.post_json(SOLANA_RPC_URL, payload) or {}
    result = response.get("result") or {}
    value = result.get("value")

    if not value:
        return None

    data_field = value.get("data")
    if not isinstance(data_field, list) or not data_field:
        return None

    encoded_data = data_field[0]

    try:
        return base64.b64decode(encoded_data)
    except Exception:
        return None


def evaluate_token_security(http: HttpClient, token: dict) -> dict:
    mint_address = token.get("address")

    if not mint_address:
        return {
            "security_status": "FAIL",
            "security_score": 0,
            "mint_authority": "UNKNOWN",
            "freeze_authority": "UNKNOWN",
            "lp_status": "NOT_CHECKED",
            "notes": ["Missing token mint address"],
        }

    raw_data = fetch_mint_account(http, mint_address)

    if raw_data is None:
        return {
            "security_status": "UNKNOWN",
            "security_score": 0,
            "mint_authority": "UNKNOWN",
            "freeze_authority": "UNKNOWN",
            "lp_status": "NOT_CHECKED",
            "notes": ["Could not fetch mint account from Solana RPC"],
        }

    parsed = _parse_spl_mint_account(raw_data)

    if not parsed.get("ok"):
        return {
            "security_status": "UNKNOWN",
            "security_score": 0,
            "mint_authority": "UNKNOWN",
            "freeze_authority": "UNKNOWN",
            "lp_status": "NOT_CHECKED",
            "notes": [parsed.get("error", "Failed to parse mint account")],
        }

    notes: list[str] = []
    security_score = 0

    if parsed["mint_authority_revoked"]:
        security_score += 40
        mint_authority = "REVOKED ✅"
    else:
        mint_authority = "ACTIVE ❌"
        notes.append("Mint authority is still active")

    if parsed["freeze_authority_disabled"]:
        security_score += 40
        freeze_authority = "DISABLED ✅"
    else:
        freeze_authority = "ACTIVE ❌"
        notes.append("Freeze authority is still active")

    if parsed["is_initialized"]:
        security_score += 20
    else:
        notes.append("Mint account is not initialized")

    # LP burn/check is intentionally not marked as PASS yet.
    # It needs pool-specific parsing and should not be faked.
    lp_status = "NOT_CHECKED"

    if security_score >= 100:
        security_status = "PASS"
    elif security_score >= 80:
        security_status = "PARTIAL_PASS"
    else:
        security_status = "FAIL"

    if not notes:
        notes.append("Mint and freeze authority checks passed")

    return {
        "security_status": security_status,
        "security_score": security_score,
        "mint_authority": mint_authority,
        "freeze_authority": freeze_authority,
        "lp_status": lp_status,
        "decimals": parsed.get("decimals"),
        "notes": notes,
    }
