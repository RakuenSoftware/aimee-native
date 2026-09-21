"""The user's fixed A–F bank intervention, independent of model/runtime code."""
import re


def banks():
    """Pairs are (logical Aimee identity role, latent payload role)."""
    c = [("target", "target"), ("d1", "d1"), ("d2", "d2"), ("d3", "d3")]
    return {"A": c[:1], "B": c[:2], "C": c, "D": list(reversed(c)),
            "E": c[1:], "F": [("target", "wrong"), *c[1:]]}


def score(case, answer, target, terminated):
    normalized = lambda text: " ".join(text.strip().casefold().split())
    exact = normalized(answer)==normalized(target)
    mentioned = bool(re.search(r"(?<!\w)"+re.escape(target)+r"(?!\w)", answer, re.IGNORECASE))
    valid = terminated and bool(answer.strip())
    return dict(exact_target=exact, target_mentioned=mentioned, valid_answer=valid,
                expected="target" if case in "ABCD" else "not_target",
                passed=valid and (exact if case in "ABCD" else not mentioned))
