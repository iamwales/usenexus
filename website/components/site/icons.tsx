import {
  BarChart3,
  Building2,
  Check,
  ClipboardCheck,
  ClipboardList,
  Clock,
  Code2,
  Cog,
  FileText,
  Github,
  Globe2,
  Handshake,
  Home,
  KeyRound,
  Lock,
  Mail,
  MessageCircle,
  RefreshCw,
  ScanSearch,
  Search,
  Shield,
  ShieldCheck,
  ShieldHalf,
  Sparkles,
  Terminal,
  TrendingUp,
  Zap
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const icons: Record<string, LucideIcon> = {
  BarChart3,
  Building2,
  Check,
  ClipboardCheck,
  ClipboardList,
  Clock,
  Code2,
  Cog,
  FileText,
  Github,
  Globe2,
  Handshake,
  Home,
  KeyRound,
  Lock,
  Mail,
  MessageCircle,
  RefreshCw,
  ScanSearch,
  Search,
  Shield,
  ShieldCheck,
  ShieldHalf,
  Sparkles,
  Terminal,
  TrendingUp,
  Zap
};

export function Icon({ name, className }: { name: string; className?: string }) {
  const Component = icons[name] ?? Sparkles;
  return <Component aria-hidden="true" className={className} />;
}

export function NexusMark() {
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      stroke="white"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
    >
      <path d="M2 7h10M7 2v10M4 4l6 6M10 4 4 10" />
    </svg>
  );
}
