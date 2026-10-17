"""The simulated backend must honour pg-jev's request/response contract and plant the flaws it claims to."""
import numpy as np

from jevbench.sim import Knobs, Truths, handle_request
from jevbench.tasks import PRODUCT_OPTIONS, PRODUCT_QUESTION, Truth, rotate


def _md5(s):
    import hashlib
    return hashlib.md5(s.encode()).hexdigest()


def _choice_request(texts, options):
    return {"model": "jev-sim", "state": {"rows": [{"narrative": t} for t in texts]},
            "questions": {f"r{i}": {"type": "choice", "instructions": f"For the record `rows[{i}]`: {PRODUCT_QUESTION}",
                                    "criteria": {o: None for o in options}} for i in range(len(texts))}}


def test_contract_shapes_and_determinism():
    texts = [f"complaint {i}" for i in range(20)]
    truths = Truths({_md5(t): Truth("mortgage", "x") for t in texts})
    req = _choice_request(texts, PRODUCT_OPTIONS)
    a1 = handle_request(Knobs(), truths, req)
    a2 = handle_request(Knobs(), truths, req)
    assert a1 == a2
    assert set(a1) == {f"r{i}" for i in range(20)}
    for ans in a1.values():
        assert ans["type"] == "choice" and ans["choice"] in PRODUCT_OPTIONS
        assert abs(sum(ans["probabilities"].values()) - 1) < 1e-4
    noul = {"state": {"condition": "the complaint is about a debt collector or about collecting a debt",
                      "rows": [{"narrative": t} for t in texts]},
            "questions": {f"r{i}": {"type": "noul", "instructions": "..."} for i in range(20)}}
    for ans in handle_request(Knobs(), truths, noul).values():
        assert ans["type"] == "noul" and 0 <= ans["noul"] <= 1


def test_first_option_bias_is_planted():
    texts = [f"complaint {i}" for i in range(400)]
    truths = Truths({_md5(t): Truth(PRODUCT_OPTIONS[i % len(PRODUCT_OPTIONS)], "") for i, t in enumerate(texts)})
    k = Knobs(first_bias=1.5)

    def p_of(option, options):
        ans = handle_request(k, truths, _choice_request(texts, options))
        return np.array([ans[f"r{i}"]["probabilities"][option] for i in range(len(texts))])

    target = PRODUCT_OPTIONS[3]
    first = p_of(target, rotate(PRODUCT_OPTIONS, 3))      # target listed first
    not_first = p_of(target, PRODUCT_OPTIONS)             # target listed fourth
    assert first.mean() > not_first.mean() + 0.02
    k0 = Knobs(first_bias=0.0)
    a = handle_request(k0, truths, _choice_request(texts, rotate(PRODUCT_OPTIONS, 3)))
    b = handle_request(k0, truths, _choice_request(texts, PRODUCT_OPTIONS))
    assert all(abs(a[q]["probabilities"][o] - b[q]["probabilities"][o]) < 1e-6 for q in a for o in PRODUCT_OPTIONS)
