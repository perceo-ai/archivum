const decisions: never[] = [];

export default function DecisionsPage() {
  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-text-primary">Decisions</h1>
      </div>
      {decisions.length === 0 && (
        <div className="text-center py-12 text-text-secondary text-sm">No decisions recorded.</div>
      )}
    </div>
  );
}
