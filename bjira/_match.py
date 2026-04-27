class AmbiguousMatch(ValueError):
    pass


class NoMatch(ValueError):
    pass


def match_transition(query, transitions):
    """Resolve a user query to a transition id.

    Match order: numeric id -> case-insensitive exact name -> case-insensitive substring.
    Ambiguous substring matches raise AmbiguousMatch with candidate list.
    """
    if query.isdigit():
        for t in transitions:
            if t["id"] == query:
                return t["id"]
        raise NoMatch(f"no transition with id={query}")

    q = query.lower()
    exact = [t for t in transitions if t["name"].lower() == q]
    if len(exact) == 1:
        return exact[0]["id"]

    # Substring matching: check if all words in query appear in the name (in order)
    query_words = q.split()
    def matches_query_words(name):
        name_lower = name.lower()
        pos = 0
        for word in query_words:
            pos = name_lower.find(word, pos)
            if pos == -1:
                return False
            pos += len(word)
        return True

    substr = [t for t in transitions if matches_query_words(t["name"])]
    if len(substr) == 1:
        return substr[0]["id"]
    if len(substr) > 1:
        candidates = ", ".join(f"{t['id']} {t['name']}" for t in substr)
        raise AmbiguousMatch(f"ambiguous (matches {len(substr)}: {candidates})")

    raise NoMatch(f"no transition matches {query!r}")


def resolve_link_type(query, link_types):
    """Return canonical link type name (case-insensitive exact match)."""
    q = query.lower()
    for lt in link_types:
        if lt["name"].lower() == q:
            return lt["name"]
    available = ", ".join(lt["name"] for lt in link_types)
    raise NoMatch(f"unknown link type {query!r}; available: {available}")
