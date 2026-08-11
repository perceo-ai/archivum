import { useState, useEffect, useCallback } from 'react';
import { Bot, Check, Copy, Mic, RefreshCw, Save, X } from 'lucide-react';
import {
  createInvite,
  getAudioSupport,
  getLlmSettings,
  listInvites,
  updateLlmSettings,
  type AudioSupportStatus,
  type InviteToken,
  type LlmSettings,
} from '../api';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';

export default function SettingsPage() {
  const [invites, setInvites] = useState<InviteToken[]>([]);
  const [audioSupport, setAudioSupport] = useState<AudioSupportStatus | null>(null);
  const [llmSettings, setLlmSettings] = useState<LlmSettings | null>(null);
  const [llmDraft, setLlmDraft] = useState({
    llm_extraction_provider: 'ollama',
    llm_synthesis_provider: 'ollama',
    llm_model: '',
    llm_synthesis_model: '',
    ollama_base_url: '',
    ollama_api_key: '',
  });
  const [loading, setLoading] = useState(true);
  const [audioLoading, setAudioLoading] = useState(true);
  const [llmLoading, setLlmLoading] = useState(true);
  const [llmSaving, setLlmSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [llmSaved, setLlmSaved] = useState(false);

  const [role, setRole] = useState<'viewer' | 'collaborator'>('viewer');
  const [expiryDays, setExpiryDays] = useState<number | null>(7);
  const [generating, setGenerating] = useState(false);
  const [generatedUrl, setGeneratedUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [copiedAudioCommand, setCopiedAudioCommand] = useState<string | null>(null);

  const fetchInvites = useCallback(async () => {
    try {
      const data = await listInvites();
      setInvites(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load invites');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAudioSupport = useCallback(async () => {
    setAudioLoading(true);
    setAudioError(null);
    try {
      const data = await getAudioSupport();
      setAudioSupport(data);
    } catch (e) {
      setAudioError(e instanceof Error ? e.message : 'Failed to load audio support status');
    } finally {
      setAudioLoading(false);
    }
  }, []);

  const fetchLlmSettings = useCallback(async () => {
    setLlmLoading(true);
    setLlmError(null);
    try {
      const data = await getLlmSettings();
      setLlmSettings(data);
      setLlmDraft({
        llm_extraction_provider: data.llm_extraction_provider,
        llm_synthesis_provider: data.llm_synthesis_provider,
        llm_model: data.llm_model,
        llm_synthesis_model: data.llm_synthesis_model,
        ollama_base_url: data.ollama_base_url,
        ollama_api_key: '',
      });
    } catch (e) {
      setLlmError(e instanceof Error ? e.message : 'Failed to load LLM settings');
    } finally {
      setLlmLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInvites();
    fetchAudioSupport();
    fetchLlmSettings();
  }, [fetchAudioSupport, fetchInvites, fetchLlmSettings]);

  async function handleGenerate() {
    setGenerating(true);
    setGeneratedUrl(null);
    setError(null);
    try {
      const result = await createInvite(role, expiryDays);
      const url = `${window.location.origin}${result.url}`;
      setGeneratedUrl(url);
      await fetchInvites();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate invite');
    } finally {
      setGenerating(false);
    }
  }

  async function handleCopy() {
    if (!generatedUrl) return;
    await navigator.clipboard.writeText(generatedUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function copyAudioCommand(key: string, value: string) {
    await navigator.clipboard.writeText(value);
    setCopiedAudioCommand(key);
    setTimeout(() => setCopiedAudioCommand(null), 2000);
  }

  async function handleSaveLlmSettings() {
    setLlmSaving(true);
    setLlmSaved(false);
    setLlmError(null);
    try {
      const next = await updateLlmSettings({
        llm_extraction_provider: llmDraft.llm_extraction_provider,
        llm_synthesis_provider: llmDraft.llm_synthesis_provider,
        llm_model: llmDraft.llm_model,
        llm_synthesis_model: llmDraft.llm_synthesis_model,
        ollama_base_url: llmDraft.ollama_base_url,
        ollama_api_key: llmDraft.ollama_api_key ? llmDraft.ollama_api_key : null,
      });
      setLlmSettings(next);
      setLlmDraft((draft) => ({ ...draft, ollama_api_key: '' }));
      setLlmSaved(true);
      setTimeout(() => setLlmSaved(false), 2400);
    } catch (e) {
      setLlmError(e instanceof Error ? e.message : 'Failed to save LLM settings');
    } finally {
      setLlmSaving(false);
    }
  }

  function formatDate(iso: string | null) {
    if (!iso) return 'Never';
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return iso;
    }
  }

  function isExpired(iso: string | null) {
    if (!iso) return false;
    return new Date(iso) < new Date();
  }

  return (
    <div className="w-full flex-1 overflow-y-auto p-4">
      <h1 className="mb-5 text-xl font-semibold text-white">Settings</h1>

      <Card className="mb-6">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Bot className="h-4 w-4" />
                LLM Provider
              </CardTitle>
              <p className="mt-1 text-xs text-text-secondary">
                Configure extraction and cited-answer synthesis providers.
              </p>
            </div>
            {llmSettings?.ollama_api_key_configured && (
              <Badge variant="success" className="text-xs">
                Key {llmSettings.ollama_api_key_masked}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {llmLoading ? (
            <p className="text-sm text-text-secondary">Loading LLM settings...</p>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <ProviderField
                  label="Extraction provider"
                  value={llmDraft.llm_extraction_provider}
                  onChange={(value) => setLlmDraft((draft) => ({ ...draft, llm_extraction_provider: value }))}
                />
                <ProviderField
                  label="Synthesis provider"
                  value={llmDraft.llm_synthesis_provider}
                  onChange={(value) => setLlmDraft((draft) => ({ ...draft, llm_synthesis_provider: value }))}
                />
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <TextField
                  label="Extraction model"
                  value={llmDraft.llm_model}
                  onChange={(value) => setLlmDraft((draft) => ({ ...draft, llm_model: value }))}
                />
                <TextField
                  label="Synthesis model"
                  value={llmDraft.llm_synthesis_model}
                  onChange={(value) => setLlmDraft((draft) => ({ ...draft, llm_synthesis_model: value }))}
                />
              </div>

              <TextField
                label="Ollama base URL"
                value={llmDraft.ollama_base_url}
                onChange={(value) => setLlmDraft((draft) => ({ ...draft, ollama_base_url: value }))}
              />

              <TextField
                label="Ollama API key"
                value={llmDraft.ollama_api_key}
                type="password"
                placeholder={llmSettings?.ollama_api_key_configured ? 'Leave blank to keep existing key' : ''}
                onChange={(value) => setLlmDraft((draft) => ({ ...draft, ollama_api_key: value }))}
              />

              {llmError && <p className="text-xs text-destructive">{llmError}</p>}
              {llmSaved && <p className="text-xs text-green-600">LLM settings saved.</p>}

              <Button onClick={handleSaveLlmSettings} disabled={llmSaving} size="sm">
                <Save className="h-3.5 w-3.5" />
                {llmSaving ? 'Saving...' : 'Save LLM Settings'}
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Mic className="h-4 w-4" />
                Audio Transcription
              </CardTitle>
              <p className="mt-1 text-xs text-text-secondary">
                Enables local audio and video transcription for uploaded media.
              </p>
            </div>
            <Button
              onClick={fetchAudioSupport}
              disabled={audioLoading}
              variant="outline"
              size="sm"
              title="Refresh audio support status"
            >
              <RefreshCw className={['h-3.5 w-3.5', audioLoading ? 'animate-spin' : ''].join(' ')} />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {audioLoading ? (
            <p className="text-sm text-text-secondary">Checking audio support...</p>
          ) : audioError ? (
            <p className="text-sm text-destructive">{audioError}</p>
          ) : audioSupport ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                {audioSupport.available ? (
                  <Badge variant="success" className="text-xs">Ready</Badge>
                ) : (
                  <Badge variant="secondary" className="text-xs">Setup needed</Badge>
                )}
                <DependencyBadge label="Whisper" ready={audioSupport.dependencies.openai_whisper} />
                <DependencyBadge label="ffmpeg" ready={audioSupport.dependencies.ffmpeg} />
              </div>

              {!audioSupport.available && (
                <div className="rounded-md border border-border bg-muted/30 p-3 space-y-3">
                  <div>
                    <p className="text-sm font-medium text-text-primary">Install audio support</p>
                    <p className="mt-1 text-xs text-text-secondary">
                      Missing: {audioSupport.missing.join(', ') || 'none'}. Default Docker images keep these packages out because Whisper/Torch are large.
                    </p>
                  </div>

                  <CommandRow
                    label="Local development"
                    value={audioSupport.commands.local}
                    copied={copiedAudioCommand === 'local'}
                    onCopy={() => copyAudioCommand('local', audioSupport.commands.local)}
                  />
                  <CommandRow
                    label="Video extraction"
                    value={audioSupport.commands.ffmpeg}
                    copied={copiedAudioCommand === 'ffmpeg'}
                    onCopy={() => copyAudioCommand('ffmpeg', audioSupport.commands.ffmpeg)}
                  />
                  <CommandRow
                    label="Docker deployment"
                    value={audioSupport.commands.docker}
                    copied={copiedAudioCommand === 'docker'}
                    onCopy={() => copyAudioCommand('docker', audioSupport.commands.docker)}
                  />
                </div>
              )}
            </>
          ) : null}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Generate Invite Link</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-1">
              <label className="text-xs text-text-secondary font-medium">Role</label>
              <div className="flex gap-2">
                {(['viewer', 'collaborator'] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setRole(r)}
                    className={[
                      'px-3 py-1.5 rounded-md text-xs font-medium border transition-colors',
                      role === r
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-background border-border text-text-secondary hover:bg-accent',
                    ].join(' ')}
                  >
                    {r.charAt(0).toUpperCase() + r.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-text-secondary font-medium">Expiry</label>
              <div className="flex gap-2">
                {[
                  { label: '7 days', value: 7 },
                  { label: '30 days', value: 30 },
                  { label: 'Never', value: null },
                ].map((opt) => (
                  <button
                    key={opt.label}
                    onClick={() => setExpiryDays(opt.value)}
                    className={[
                      'px-3 py-1.5 rounded-md text-xs font-medium border transition-colors',
                      expiryDays === opt.value
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-background border-border text-text-secondary hover:bg-accent',
                    ].join(' ')}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <Button onClick={handleGenerate} disabled={generating} size="sm">
              {generating ? 'Generating...' : 'Generate Invite Link'}
            </Button>
          </div>

          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}

          {generatedUrl && (
            <div className="flex items-center gap-2 mt-2">
              <input
                readOnly
                value={generatedUrl}
                className="flex-1 h-8 rounded-md border border-border bg-background px-3 text-xs text-text-secondary font-mono focus:outline-none"
              />
              <Button onClick={handleCopy} variant="outline" size="sm">
                {copied ? 'Copied!' : 'Copy'}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Invite Tokens</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-text-secondary">Loading...</p>
          ) : invites.length === 0 ? (
            <p className="text-sm text-text-secondary">No invite tokens yet.</p>
          ) : (
            <div className="space-y-2">
              {invites.map((invite) => {
                const expired = isExpired(invite.expires_at);
                return (
                  <div
                    key={invite.id}
                    className="flex items-center justify-between gap-3 py-2 border-b border-border last:border-0"
                  >
                    <code className="text-xs text-text-secondary font-mono">
                      {invite.token.slice(0, 16)}…
                    </code>
                    <div className="flex items-center gap-2 ml-auto flex-wrap justify-end">
                      <Badge variant="outline" className="text-xs">
                        {invite.role}
                      </Badge>
                      {invite.used ? (
                        <Badge variant="secondary" className="text-xs">Used</Badge>
                      ) : expired ? (
                        <Badge variant="destructive" className="text-xs">Expired</Badge>
                      ) : (
                        <Badge variant="success" className="text-xs">Active</Badge>
                      )}
                      <span className="text-xs text-text-secondary whitespace-nowrap">
                        Expires: {formatDate(invite.expires_at)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function DependencyBadge({ label, ready }: { label: string; ready: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-text-secondary">
      {ready ? <Check className="h-3 w-3 text-green-500" /> : <X className="h-3 w-3 text-destructive" />}
      {label}
    </span>
  );
}

function ProviderField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-1">
      <span className="text-xs font-medium text-text-secondary">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <option value="anthropic">Anthropic</option>
        <option value="openrouter">OpenRouter</option>
        <option value="openai_compat">OpenAI-compatible</option>
        <option value="ollama">Ollama</option>
      </select>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="space-y-1">
      <span className="text-xs font-medium text-text-secondary">{label}</span>
      <Input
        value={value}
        type={type}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 text-sm"
      />
    </label>
  );
}

function CommandRow({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-text-secondary">{label}</p>
        <code className="mt-1 block truncate rounded border border-border bg-background px-2 py-1.5 text-xs text-text-secondary">
          {value}
        </code>
      </div>
      <Button onClick={onCopy} variant="outline" size="sm">
        <Copy className="h-3.5 w-3.5" />
        {copied ? 'Copied' : 'Copy'}
      </Button>
    </div>
  );
}
