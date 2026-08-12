import { Download, FileCode2, MoreHorizontal, Share2, Trash2 } from 'lucide-react';
import { Button } from './ui/Button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/DropdownMenu';

interface PageActionsProps {
  slug: string;
  disabled: boolean;
  shareLoading: boolean;
  onSave: () => void;
  onShare: () => void;
  onDelete: () => void;
}

export default function PageActions({
  slug,
  disabled,
  shareLoading,
  onSave,
  onShare,
  onDelete,
}: PageActionsProps) {
  function handleExport(format: 'html' | 'pdf') {
    window.open(`/api/export?slug=${encodeURIComponent(slug)}&format=${format}`, '_blank');
  }

  return (
    <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
      <Button variant="secondary" size="sm" onClick={onSave} disabled={disabled}>
        Save
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={onShare}
        disabled={disabled || shareLoading}
        aria-label="Share page"
        title="Share page"
      >
        <Share2 className="h-4 w-4" />
        <span className="hidden sm:inline">{shareLoading ? 'Sharing...' : 'Share'}</span>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => handleExport('html')}
        disabled={disabled}
        aria-label="Export page as HTML"
        title="Export page as HTML"
      >
        <FileCode2 className="h-4 w-4" />
        <span className="hidden lg:inline">HTML</span>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => handleExport('pdf')}
        disabled={disabled}
        aria-label="Export page as PDF"
        title="Export page as PDF"
      >
        <Download className="h-4 w-4" />
        <span className="hidden lg:inline">PDF</span>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" disabled={disabled} aria-label="More page actions">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={onDelete} className="text-destructive">
            <Trash2 className="h-4 w-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
