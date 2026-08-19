const activity: never[] = [];

export default function ActivityPage() {
  return (
    <div className="w-full flex-1 overflow-y-auto p-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-white">Activity</h1>
      </div>
      {activity.length === 0 && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          No activity yet. Import a source, edit a note, or approve memory to start the timeline.
        </div>
      )}
    </div>
  );
}
