import { useState, useEffect, useCallback } from 'react';
import { Check, Copy, Mic, RefreshCw, X } from 'lucide-react';
import {
  createInvite,
  getAudioSupport,
  listInvites,
  type AudioSupportStatus,
  type InviteToken,
} from '../api';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';

export default function SettingsPage() {
  const [invites, setInvites] = useState<InviteToken[]>([]);
  const [audioSupport, setAudioSupport] = useState<AudioSupportStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [audioLoading, setAudioLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);

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

  useEffect(() => {
    fetchInvites();
    fetchAudioSupport();
  }, [fetchAudioSupport, fetchInvites]);

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
    <div className="flex-1 overflow-y-auto p-6 max-w-3xl mx-auto w-full">
      <h1 className="text-xl font-semibold text-text-primary mb-6">Settings</h1>

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
