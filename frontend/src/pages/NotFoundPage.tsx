import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="h-full flex items-center justify-center" style={{ backgroundColor: '#1e1e2e' }}>
      <div className="text-center">
        <div className="text-text-primary text-lg font-semibold mb-2">Not found</div>
        <Link to="/" className="text-accent hover:underline text-sm">
          Go home
        </Link>
      </div>
    </div>
  );
}

