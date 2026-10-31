"""Identifier crosswalk and resolver, built on demand from the IPEDS directory (no stored crosswalk).

Rules:
- Identifier matches are exact. Name matches are scored and labeled; they are never promoted to a
  single answer unless exactly one candidate matches the normalized name exactly.
- One identifier mapping to several UNITIDs (OPEID6 branches, shared EINs/UEIs) is returned as
  ambiguous with every candidate; this module never picks one.
"""
import difflib
import re
from collections import defaultdict

SENTINELS = {None, "", "-1", "-2", "-3", -1, -2, -3}
CONTROL = {1: "public", 2: "private_nonprofit", 3: "private_for_profit"}
CONTROL_CODE = {v: k for k, v in CONTROL.items()}

UNITID_RE = re.compile(r"^\d{6}$")
OPEID8_RE = re.compile(r"^\d{8}$")
EIN_RE = re.compile(r"^\d{2}-?\d{7}$")
UEI_RE = re.compile(r"^[A-Za-z0-9]{12}$")
DOMAIN_RE = re.compile(r"^(?=.{4,100}$)([a-z0-9-]+\.)+[a-z]{2,}$")


def clean(v):
    return None if v in SENTINELS else v


def norm_ein(v) -> str | None:
    v = clean(v)
    digits = re.sub(r"\D", "", str(v)) if v is not None else ""
    return digits.zfill(9) if digits and len(digits) <= 9 else None


def norm_domain(v) -> str | None:
    v = clean(v)
    if not v:
        return None
    v = re.sub(r"^https?://", "", str(v).strip().lower())
    v = v.split("/")[0].split("?")[0]
    v = re.sub(r"^www\.", "", v)
    return v if DOMAIN_RE.match(v) else None


def split_ueis(v) -> list[str]:
    v = clean(v)
    return [u for u in re.split(r"[,;\s]+", str(v).upper()) if UEI_RE.match(u)] if v else []


def norm_name(v: str) -> str:
    v = v.lower().replace("&", " and ")
    v = re.sub(r"[^a-z0-9 ]", " ", v)
    return " ".join(t for t in v.split() if t != "the")


def is_active(r: dict) -> bool:
    return r.get("currently_active_ipeds") == 1


def candidate_view(r: dict, basis: str, score: float | None = None, notes: list[str] | None = None) -> dict:
    return {
        "unitid": str(r["unitid"]),
        "name": r["inst_name"],
        "city": r.get("city"),
        "state": r.get("state_abbr"),
        "opeid": clean(r.get("opeid")),
        "ein": norm_ein(r.get("ein")),
        "ueis": split_ueis(r.get("ueis")),
        "domain": norm_domain(r.get("url_school")),
        "active": is_active(r),
        "match_basis": basis,
        "score": score,
        "notes": notes or [],
    }


class Index:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.by_unitid = {str(r["unitid"]): r for r in rows}
        self.by_opeid8, self.by_opeid6 = defaultdict(list), defaultdict(list)
        self.by_ein, self.by_uei, self.by_domain = defaultdict(list), defaultdict(list), defaultdict(list)
        for r in rows:
            ope = clean(r.get("opeid"))
            if ope:
                self.by_opeid8[ope].append(r)
                self.by_opeid6[ope[:6]].append(r)
            ein = norm_ein(r.get("ein"))
            if ein:
                self.by_ein[ein].append(r)
            for u in split_ueis(r.get("ueis")):
                self.by_uei[u].append(r)
            dom = norm_domain(r.get("url_school"))
            if dom:
                self.by_domain[dom].append(r)
        self._names = [(norm_name(r["inst_name"]), norm_name(clean(r.get("inst_alias")) or ""), r) for r in rows]

    def system_members(self, r: dict) -> list[dict]:
        name = clean(r.get("inst_system_name"))
        if not name:
            return []
        return [x for x in self.rows if x.get("inst_system_name") == name and is_active(x)]

    def same_opeid6(self, r: dict) -> list[dict]:
        ope = clean(r.get("opeid"))
        return [x for x in self.by_opeid6.get(ope[:6], []) if x is not r] if ope else []


def _result(query, kind, cands, state=None, extra_notes=None):
    if state:
        cands = [c for c in cands if (c["state"] or "").upper() == state.upper()]
    exact = [c for c in cands if c["match_basis"].startswith("exact")]
    resolved = len(cands) == 1 and bool(exact)
    notes = list(extra_notes or [])
    if len(cands) > 1:
        notes.append("Multiple institutions match; none was chosen. Disambiguate with a UNITID or state.")
    if not cands:
        notes.append("No match. Nothing was guessed.")
    return {"query": query, "kind": kind, "resolved": resolved, "candidates": cands, "notes": notes}


def resolve(index: Index, query: str, kind: str = "auto", state: str | None = None) -> dict:
    q = query.strip()
    if kind == "auto":
        if UNITID_RE.match(q):
            kind = "unitid_or_opeid6"
        elif OPEID8_RE.match(q):
            kind = "opeid"
        elif EIN_RE.match(q):
            kind = "ein"
        elif UEI_RE.match(q) and re.search(r"\d", q) and re.search(r"[A-Za-z]", q) and q.upper() == q:
            kind = "uei"
        elif DOMAIN_RE.match(norm_domain(q) or ""):
            kind = "domain"
        else:
            kind = "name"

    cands: list[dict] = []
    if kind in ("unitid", "unitid_or_opeid6"):
        if not UNITID_RE.match(q):
            raise ValueError("UNITID must be exactly 6 digits.")
        if q in index.by_unitid:
            cands.append(candidate_view(index.by_unitid[q], "exact_unitid", 1.0))
        if kind == "unitid_or_opeid6":
            for r in index.by_opeid6.get(q, []):
                if str(r["unitid"]) != q:
                    cands.append(candidate_view(r, "exact_opeid6", 1.0, ["Shares a 6-digit OPEID; one OPEID can cover several campuses."]))
            if cands and len({c["unitid"] for c in cands}) > 1 and q in index.by_unitid:
                return _result(q, kind, cands, state, ["A 6-digit value can be a UNITID or an OPEID6; both interpretations matched."])
    elif kind == "opeid":
        if not (OPEID8_RE.match(q) or UNITID_RE.match(q)):
            raise ValueError("OPEID must be 8 digits (or 6 for the OPEID6 prefix).")
        rows = index.by_opeid8.get(q, []) if len(q) == 8 else index.by_opeid6.get(q, [])
        cands = [candidate_view(r, "exact_opeid8" if len(q) == 8 else "exact_opeid6") for r in rows]
        if len(cands) > 1:
            for c in cands:
                c["notes"].append("One-to-many OPEID mapping.")
    elif kind == "ein":
        if not EIN_RE.match(q):
            raise ValueError("EIN must be 9 digits (optionally XX-XXXXXXX).")
        cands = [candidate_view(r, "exact_ein") for r in index.by_ein.get(norm_ein(q), [])]
    elif kind == "uei":
        if not UEI_RE.match(q):
            raise ValueError("UEI must be 12 letters/digits.")
        cands = [candidate_view(r, "exact_uei") for r in index.by_uei.get(q.upper(), [])]
    elif kind == "domain":
        dom = norm_domain(q)
        if not dom:
            raise ValueError("Not a valid web domain.")
        rows = index.by_domain.get(dom, [])
        cands = [candidate_view(r, "exact_domain") for r in rows]
        if not cands and dom.count(".") >= 2:
            parent = dom.split(".", 1)[1]
            cands = [candidate_view(r, "parent_domain", 0.8, [f"Matched on parent domain {parent}."]) for r in index.by_domain.get(parent, [])]
    else:  # name
        return _resolve_name(index, q, state)
    return _result(q, kind, cands, state)


def _resolve_name(index: Index, q: str, state: str | None) -> dict:
    nq = norm_name(q)
    if not nq:
        raise ValueError("Name has no searchable text.")
    scored = []
    for nname, nalias, r in index._names:
        if state and (r.get("state_abbr") or "").upper() != state.upper():
            continue
        if nq == nname:
            scored.append((1.0, "exact_name", r))
        elif nalias and nq == nalias:
            scored.append((0.97, "exact_alias", r))
        elif set(nq.split()) <= set(nname.split()):
            scored.append((0.85 + 0.1 * len(nq) / max(len(nname), 1), "name_contains", r))
        else:
            ratio = difflib.SequenceMatcher(None, nq, nname).ratio()
            if ratio >= 0.75:
                scored.append((round(ratio * 0.9, 3), "fuzzy_name", r))
    scored.sort(key=lambda t: (-t[0], not is_active(t[2]), t[2]["inst_name"]))
    if scored and scored[0][0] >= 0.97:  # exact name/alias hits: drop weaker near-misses
        scored = [t for t in scored if t[0] >= 0.97]
    cands = []
    for score, basis, r in scored[:10]:
        notes = ["Fuzzy match on name; verify before relying on it."] if basis == "fuzzy_name" else []
        if not is_active(r):
            notes.append("Not currently active in IPEDS.")
        cands.append(candidate_view(r, basis, round(score, 3), notes))
    exact = [c for c in cands if c["match_basis"] == "exact_name" and c["active"]]
    out = _result(q, "name", cands, None)
    # Resolve only if exactly one active institution matches the name exactly.
    out["resolved"] = len(exact) == 1 and sum(1 for c in cands if c["score"] == 1.0) == 1
    if len(exact) > 1:
        out["notes"].append("Several institutions share this exact name; add a state.")
    return out
