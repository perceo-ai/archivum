from archivum.capture.schema import Conversation, Outcome, ToolCall, Turn
from archivum.memory.skills import extract_skill, render_skill_markdown, skill_slug


def _call(name, ok=True, **arguments):
    return ToolCall(name=name, arguments=arguments, result="done", ok=ok)


def _conv(turns, outcomes=()):
    return Conversation(
        session_id="s1",
        interface="claude_code_native",
        started_at="2026-08-12T00:00:00Z",
        turns=tuple(turns),
        outcomes=tuple(outcomes),
    )


def _working_session(**kwargs):
    return _conv(
        [
            Turn(role="user", text="Set up the deploy pipeline. Then verify it."),
            Turn(
                role="assistant",
                text="On it",
                tool_calls=(
                    _call("Write", file_path="/deploy.yml"),
                    _call("Bash", command="docker compose up -d"),
                    _call("Bash", command="pytest tests -q"),
                ),
            ),
        ],
        **kwargs,
    )


def test_prose_without_tool_calls_is_not_a_skill():
    conv = _conv(
        [
            Turn(role="user", text="How do I deploy?"),
            Turn(role="assistant", text="First build, then run compose, then test."),
        ]
    )
    assert extract_skill(conv) is None


def test_too_few_tool_calls_is_not_a_skill():
    conv = _conv(
        [
            Turn(role="user", text="Do the thing"),
            Turn(role="assistant", text="ok", tool_calls=(_call("Read", path="/a"),)),
        ]
    )
    assert extract_skill(conv) is None


def test_failed_tool_calls_do_not_count_toward_the_gate():
    conv = _conv(
        [
            Turn(role="user", text="Do the thing"),
            Turn(
                role="assistant",
                text="ok",
                tool_calls=(
                    _call("Bash", ok=False, command="a"),
                    _call("Bash", ok=False, command="b"),
                    _call("Bash", command="c"),
                ),
            ),
        ]
    )
    assert extract_skill(conv) is None


def test_recorded_failure_blocks_skill_extraction():
    conv = _working_session(outcomes=(Outcome(task="Deploy", status="failure"),))
    assert extract_skill(conv) is None


def test_steps_come_from_recorded_tool_calls_in_order():
    draft = extract_skill(_working_session())
    assert draft is not None
    assert [step.tool for step in draft.steps] == ["Write", "Bash", "Bash"]
    assert draft.steps[1].summary == "Bash(docker compose up -d)"
    assert draft.tool_call_count == 3


def test_duplicate_identical_calls_collapse_into_one_step():
    conv = _conv(
        [
            Turn(role="user", text="Run the checks"),
            Turn(
                role="assistant",
                text="ok",
                tool_calls=(
                    _call("Bash", command="pytest -q"),
                    _call("Bash", command="pytest -q"),
                    _call("Bash", command="ruff check"),
                    _call("Read", path="/x"),
                ),
            ),
        ]
    )
    draft = extract_skill(conv)
    assert [step.summary for step in draft.steps] == [
        "Bash(pytest -q)",
        "Bash(ruff check)",
        "Read(/x)",
    ]


def test_validation_is_recognised_from_verification_steps():
    draft = extract_skill(_working_session())
    assert any("pytest" in item for item in draft.validation)


def test_success_outcome_and_validation_raise_confidence():
    plain = extract_skill(_working_session())
    verified = extract_skill(
        _working_session(outcomes=(Outcome(task="Deploy", status="success"),))
    )
    assert verified.confidence > plain.confidence
    assert "Deploy — success" in verified.validation


def test_trigger_and_name_come_from_the_users_request():
    draft = extract_skill(_working_session())
    assert draft.trigger.startswith("Set up the deploy pipeline")
    assert draft.name == "Set up the deploy pipeline"
    assert draft.slug == "set-up-the-deploy-pipeline"


def test_session_without_a_user_request_has_no_trigger():
    conv = _conv(
        [
            Turn(
                role="assistant",
                text="working",
                tool_calls=(
                    _call("Bash", command="a"),
                    _call("Bash", command="b"),
                    _call("Bash", command="c"),
                ),
            )
        ]
    )
    assert extract_skill(conv) is None


def test_markdown_is_editable_and_records_provenance():
    draft = extract_skill(_working_session())
    markdown = render_skill_markdown(draft, provenance="From source `source:1`.")
    assert "type: skill" in markdown
    assert "## Steps" in markdown
    assert "1. `Write(/deploy.yml)`" in markdown
    assert "From source `source:1`." in markdown


def test_markdown_says_so_when_nothing_was_verified():
    conv = _conv(
        [
            Turn(role="user", text="Write three files"),
            Turn(
                role="assistant",
                text="ok",
                tool_calls=(
                    _call("Write", file_path="/a"),
                    _call("Write", file_path="/b"),
                    _call("Write", file_path="/c"),
                ),
            ),
        ]
    )
    markdown = render_skill_markdown(extract_skill(conv), provenance="p")
    assert "No verification step was recorded" in markdown


def test_skill_slug_is_url_safe():
    assert skill_slug("Deploy the *whole* stack!") == "deploy-the-whole-stack"
    assert skill_slug("!!!") == "skill"
