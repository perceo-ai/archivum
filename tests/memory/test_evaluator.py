import json

import pytest

from archivum.capture.schema import Conversation, Turn
from archivum.config import Settings
from archivum.memory import evaluator
from archivum.memory.atoms import Atom, extract_atoms
from archivum.memory.evaluator import (
    AtomEvaluation,
    blend_confidence,
    evaluate_conversation,
)


def _conversation():
    return Conversation(
        session_id="s1",
        interface="claude_code_native",
        started_at="2026-08-12T00:00:00Z",
        turns=(Turn(role="user", text="I prefer uv over pip. Never commit secrets."),),
    )


def _response(payload) -> str:
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_evaluation_parses_scores_types_and_proposals(monkeypatch):
    conversation = _conversation()
    atoms = extract_atoms(conversation)
    payload = {
        "atoms": [
            {
                "index": 0,
                "keep": True,
                "semantic_type": "preference",
                "scores": {
                    "human_relevance": 0.9,
                    "future_utility": 0.8,
                    "durability": 0.9,
                    "specificity": 0.7,
                    "novelty": 0.6,
                },
                "rationale": "Tooling preference the owner restated.",
                "durability_estimate": "long",
            }
        ],
        "proposed": [
            {
                "text": "The owner treats secret hygiene as a hard rule.",
                "semantic_type": "principle",
                "turn_index": 0,
                "rationale": "Restates the constraint as a durable principle.",
            }
        ],
    }

    async def fake_chat(settings, *, system, user):
        assert "candidate atoms" in user
        return _response(payload)

    monkeypatch.setattr(evaluator, "_chat", fake_chat)

    result = await evaluate_conversation(conversation, atoms, settings=Settings())

    assert result is not None
    assert result.evaluations[0].semantic_type == "preference"
    assert result.evaluations[0].scores["human_relevance"] == 0.9
    assert result.proposed[0].semantic_type == "principle"


@pytest.mark.asyncio
async def test_evaluation_failure_falls_back_to_none(monkeypatch):
    conversation = _conversation()
    atoms = extract_atoms(conversation)

    async def broken_chat(settings, *, system, user):
        raise RuntimeError("provider down")

    monkeypatch.setattr(evaluator, "_chat", broken_chat)
    assert await evaluate_conversation(conversation, atoms, settings=Settings()) is None

    async def junk_chat(settings, *, system, user):
        return "not json at all"

    monkeypatch.setattr(evaluator, "_chat", junk_chat)
    assert await evaluate_conversation(conversation, atoms, settings=Settings()) is None


def test_blend_confidence_averages_and_caps_vetoed_atoms():
    kept = AtomEvaluation(
        keep=True,
        semantic_type="preference",
        scores={"human_relevance": 1.0, "future_utility": 0.6},
        rationale="",
        durability_estimate="long",
    )
    assert blend_confidence(0.8, kept) == 0.8

    vetoed = AtomEvaluation(
        keep=False,
        semantic_type=None,
        scores={"human_relevance": 1.0},
        rationale="",
        durability_estimate="",
    )
    # A veto must land below any promotion threshold: review-only.
    assert blend_confidence(0.9, vetoed) <= 0.1


def test_parse_response_ignores_invalid_entries():
    raw = json.dumps(
        {
            "atoms": [
                {"index": 99, "keep": True},
                {"index": 0, "semantic_type": "not-a-type", "keep": True},
                "junk",
            ],
            "proposed": [
                {"text": "", "semantic_type": "fact"},
                {"text": "Valid", "semantic_type": "unknown"},
            ],
        }
    )
    result = evaluator._parse_response(raw, atom_count=1)
    assert result is not None
    assert result.evaluations[0].semantic_type is None
    assert result.proposed == []


def test_extract_json_handles_fenced_output():
    raw = "Here you go:\n```json\n{\"atoms\": [], \"proposed\": []}\n```"
    assert evaluator._extract_json(raw) == {"atoms": [], "proposed": []}
