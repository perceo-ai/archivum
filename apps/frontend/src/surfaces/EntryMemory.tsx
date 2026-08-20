import { useEffect, useState } from 'react';
import { listMemoryAssets, setMemoryAssetStatus, type MemoryAsset } from '../api';
import { useToast } from '../components/ui/Toast';
import { cn } from '../lib/cn';

/**
 * What Archivum remembers from this entry.
 *
 * Memory lives on the page it came from rather than in a Memory section, so
 * "what my agents know" is inspectable where you'd naturally look. The switch
 * writes asset status straight through: active means agents may use it.
 */

export default function EntryMemory({ slug }: { slug: string }) {
  const [assets, setAssets] = useState<MemoryAsset[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const { push } = useToast();

  useEffect(() => {
    let cancelled = false;
    listMemoryAssets({ page_slug: slug })
      .then((next) => {
        if (!cancelled) setAssets(next);
      })
      .catch(() => {
        if (!cancelled) setAssets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  async function toggle(asset: MemoryAsset) {
    const next = asset.status === 'active' ? 'archived' : 'active';
    setBusy(asset.id);
    try {
      const updated = await setMemoryAssetStatus(asset.id, next);
      setAssets((prev) => (prev ?? []).map((item) => (item.id === asset.id ? updated : item)));
      push({
        kind: 'success',
        title: next === 'active' ? 'Agents can use this' : 'Turned off for agents',
        description: asset.name,
      });
    } catch (error) {
      push({
        kind: 'error',
        title: "Couldn't change that",
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setBusy(null);
    }
  }

  // Nothing distilled from this page yet is the common case, and an empty
  // section here would be noise.
  if (!assets || assets.length === 0) return null;

  return (
    <div className="memblock">
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12 }}>
        <span className="eyebrow">What Archivum remembers from this</span>
        <span className="chip" style={{ marginLeft: 'auto' }}>
          {assets.length} memor{assets.length === 1 ? 'y' : 'ies'}
        </span>
      </div>

      {assets.map((asset) => {
        const disputed = asset.conflict_lineage.length > 0;
        return (
          <div
            key={asset.id}
            className="mem"
            style={
              disputed
                ? { borderColor: 'color-mix(in srgb, var(--warn) 40%, var(--border))' }
                : undefined
            }
          >
            <button
              type="button"
              className={cn('toggle', asset.status === 'active' && 'on')}
              disabled={busy === asset.id}
              aria-label={asset.status === 'active' ? 'Turn off for agents' : 'Turn on for agents'}
              onClick={() => void toggle(asset)}
            />
            <div className="txt">
              {asset.summary || asset.name}
              <div className="sub">
                <span
                  className={cn(
                    'chip',
                    disputed ? 'chip-warn' : asset.status === 'active' ? 'chip-ok' : '',
                  )}
                >
                  {disputed ? 'disputed' : asset.status === 'active' ? 'live' : 'off'}
                </span>
                <span>
                  {asset.layer} · {asset.citations.length} citation
                  {asset.citations.length === 1 ? '' : 's'}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
