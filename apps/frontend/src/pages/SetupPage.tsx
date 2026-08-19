import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getMcpSettings,
  getOwner,
  registerMemoryAsset,
  upsertMemoryScope,
  type McpSettings,
  type OwnerProfile,
} from '../api';
import { useToast } from '../components/ui/Toast';
import { Icon } from '../shell/Icon';
import { cn } from '../lib/cn';

/**
 * Six steps that end with `person:self` existing and knowing three things.
 *
 * Every step writes through to a real endpoint — naming yourself upserts the
 * self scope, the three answers become memory assets on that scope. Nothing
 * here is a mock, and every step can be skipped.
 */

const STEPS = [
  { title: 'Who this is for', hint: 'The person everything hangs off' },
  { title: 'Tell it about you', hint: 'Your first three memories' },
  { title: 'Let your agents in', hint: 'And what they can read' },
  { title: 'Done', hint: 'Open the vault' },
];

const QUESTIONS = [
  {
    key: 'role',
    label: 'What do you do?',
    placeholder: 'Engineer. I build local-first developer tools.',
  },
  {
    key: 'focus',
    label: "What are you in the middle of right now?",
    placeholder: 'Retrieval quality — hybrid search and a review loop that feels effortless.',
  },
  {
    key: 'rules',
    label: 'Anything an agent should never do?',
    placeholder: 'Never write to my vault without asking. Never touch People or Daily notes.',
  },
];

export default function SetupPage() {
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [owner, setOwner] = useState<OwnerProfile | null>(null);
  const [mcp, setMcp] = useState<McpSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();
  const { push } = useToast();

  useEffect(() => {
    getOwner()
      .then((next) => {
        setOwner(next);
        if (!next.needs_setup) setName(next.name);
      })
      .catch(() => undefined);
    getMcpSettings()
      .then(setMcp)
      .catch(() => undefined);
  }, []);

  const initials =
    name
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('') || '··';

  async function saveIdentity() {
    if (!name.trim()) return;
    await upsertMemoryScope({
      id: 'person:self',
      scope_type: 'human',
      name: name.trim(),
    });
  }

  async function saveAnswers() {
    const written = QUESTIONS.filter((question) => answers[question.key]?.trim());
    for (const question of written) {
      await registerMemoryAsset({
        id: `memory:persona:${question.key}`,
        asset_type: 'persona',
        layer: 'L3',
        name: question.label,
        summary: answers[question.key].trim(),
        body: answers[question.key].trim(),
        // Written by the owner, so it is live immediately rather than a draft
        // awaiting review: you do not need to approve your own words.
        status: 'active',
      });
    }
    return written.length;
  }

  async function next() {
    if (saving) return;
    setSaving(true);
    try {
      if (step === 0) await saveIdentity();
      if (step === 1) {
        const written = await saveAnswers();
        if (written > 0) {
          push({
            kind: 'success',
            title: `${written} memor${written === 1 ? 'y' : 'ies'} written about you`,
          });
        }
      }
      if (step === STEPS.length - 1) {
        navigate('/');
        return;
      }
      setStep((current) => current + 1);
    } catch (error) {
      push({
        kind: 'error',
        title: "That didn't save",
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="setup">
      <aside className="rail">
        <div className="brand">
          <span className="m">A</span>
          <b>Archivum</b>
        </div>
        <div className="steps">
          {STEPS.map((entry, index) => (
            <div
              key={entry.title}
              className={cn('step', index === step && 'on', index < step && 'done')}
            >
              <span className="n">
                {index < step ? <Icon name="check" size={12} /> : index + 1}
              </span>
              <span className="t">
                {entry.title}
                <span className="s">{entry.hint}</span>
              </span>
            </div>
          ))}
        </div>
        <div className="rail-foot">
          <div className="bar">
            <span style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} />
          </div>
          <p>
            Takes about a minute. Everything here is changeable later — nothing you pick now is
            permanent.
          </p>
        </div>
      </aside>

      <main className="pane">
        <div className="pane-top">
          <span style={{ fontSize: 'var(--t-12)', color: 'var(--text-3)' }}>
            Step {step + 1} of {STEPS.length}
          </span>
        </div>

        <div className="card-wrap">
          {step === 0 && (
            <section className="screen on">
              <div className="eyebrow-s">Start here</div>
              <h1>Everything in Archivum hangs off one person.</h1>
              <p className="lede">
                Your notes, the things you decide, the people you talk to, what your agents are
                allowed to know — all of it is stored <b>relative to you</b>. So the first thing the
                vault needs is you.
              </p>

              <div className="selfcard">
                <div className="selfnode">{initials}</div>
                <div>
                  <div className="t">{name.trim() || 'Your name'}</div>
                  <div className="s">the centre of your graph · everything else links back here</div>
                </div>
              </div>

              <div className="field">
                <label htmlFor="setup-name">What should Archivum call you?</label>
                <input
                  id="setup-name"
                  className="inp"
                  value={name}
                  autoFocus
                  placeholder="Your name"
                  onChange={(event) => setName(event.target.value)}
                />
                <div className="help">
                  Stored as the name of the <code>person:self</code> scope, and used as the root of
                  your graph.
                </div>
              </div>
            </section>
          )}

          {step === 1 && (
            <section className="screen on">
              <div className="eyebrow-s">Your first memories</div>
              <h1>Tell it three things about you.</h1>
              <p className="lede">
                This becomes the context every agent gets before it touches your vault. Write like
                you are briefing a new colleague. <b>You can edit or delete any of it later</b> — it
                is just memory on your own entry.
              </p>

              {QUESTIONS.map((question) => (
                <div className="field" key={question.key}>
                  <label htmlFor={`q-${question.key}`}>{question.label}</label>
                  <textarea
                    id={`q-${question.key}`}
                    className="inp"
                    rows={2}
                    placeholder={question.placeholder}
                    value={answers[question.key] ?? ''}
                    onChange={(event) =>
                      setAnswers((prev) => ({ ...prev, [question.key]: event.target.value }))
                    }
                  />
                </div>
              ))}
            </section>
          )}

          {step === 2 && (
            <section className="screen on">
              <div className="eyebrow-s">Agents</div>
              <h1>Let your tools read the vault.</h1>
              <p className="lede">
                Archivum speaks MCP, so the same notes are available to whatever you already use.
                Agents propose; you decide. Nothing an agent writes enters your memory without you.
              </p>

              <div className="mcp-row">
                <span className="opt-ic">
                  <Icon name="bot" />
                </span>
                <div>
                  <div className="t">MCP endpoint</div>
                  <div className="s">
                    {mcp ? mcp.endpoint : 'checking…'}
                  </div>
                </div>
              </div>

              {mcp && (
                <div className="codebox">
                  {JSON.stringify(mcp.client_config, null, 2)}
                </div>
              )}

              <div className="help" style={{ marginTop: 12 }}>
                Point Claude Desktop, Claude Code, or Cursor at that endpoint. What each agent can
                read is managed per memory, on the entry it came from.
                {mcp && !mcp.api_key_configured && (
                  <>
                    {' '}
                    <b style={{ color: 'var(--warn)' }}>
                      No MCP key is configured yet, so the endpoint is open — set MCP_API_KEY before
                      exposing it.
                    </b>
                  </>
                )}
              </div>
            </section>
          )}

          {step === 3 && (
            <section className="screen on">
              <div className="eyebrow-s">Ready</div>
              <h1>Your vault is standing up.</h1>
              <div className="done-list">
                <div className="done-item">
                  <span className="tick">
                    <Icon name="check" size={12} />
                  </span>
                  <span>
                    <b>{name.trim() || 'You'}</b> is the root of the graph.
                  </span>
                </div>
                <div className="done-item">
                  <span className="tick">
                    <Icon name="check" size={12} />
                  </span>
                  <span>
                    <b>{owner?.pages ?? 0} entries</b> indexed from your vault.
                  </span>
                </div>
                <div className="done-item">
                  <span className="tick">
                    <Icon name="check" size={12} />
                  </span>
                  <span>
                    <b>{Object.values(answers).filter((value) => value.trim()).length} memories</b>{' '}
                    written about you — the context every agent starts from.
                  </span>
                </div>
              </div>
            </section>
          )}
        </div>

        <div className="pane-foot">
          {step > 0 && (
            <button type="button" className="btn btn-outline btn-lg" onClick={() => setStep(step - 1)}>
              Back
            </button>
          )}
          <div className="right">
            {step > 0 && step < STEPS.length - 1 && (
              <button type="button" className="skip" onClick={() => setStep(step + 1)}>
                Skip this
              </button>
            )}
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={saving || (step === 0 && !name.trim())}
              onClick={() => void next()}
            >
              {step === STEPS.length - 1 ? 'Open your vault' : 'Continue'}
              {step === STEPS.length - 1 && <Icon name="arrowRight" />}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
