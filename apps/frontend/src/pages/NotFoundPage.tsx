import { Link } from 'react-router-dom';
import { Card } from '../components/ui/Card';

export default function NotFoundPage() {
  return (
    <div className="h-full flex items-center justify-center bg-bg">
      <Card className="text-center p-6">
        <div className="text-foreground text-lg font-semibold mb-2">Not found</div>
        <Link to="/" className="text-accent hover:underline text-sm">
          Go home
        </Link>
      </Card>
    </div>
  );
}

