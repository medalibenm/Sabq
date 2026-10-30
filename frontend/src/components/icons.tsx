import type { ReactNode } from "react";

function Svg({
  size = 16,
  width = 2,
  className,
  children,
}: {
  size?: number;
  width?: number;
  className?: string;
  children: ReactNode;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

type P = { size?: number; width?: number; className?: string };

export const Close = (p: P) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
);
export const Search = (p: P) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  </Svg>
);
export const Funnel = (p: P) => (
  <Svg {...p}>
    <path d="M4 5h16l-6 8v5l-4 2v-7z" />
  </Svg>
);
export const External = (p: P) => (
  <Svg {...p}>
    <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Svg>
);
export const Pencil = (p: P) => (
  <Svg {...p}>
    <path d="M4 20h4L19 9l-4-4L4 16z" />
  </Svg>
);
export const Layers = (p: P) => (
  <Svg {...p}>
    <path d="M12 3l9 5-9 5-9-5z" />
    <path d="M3 13l9 5 9-5" />
  </Svg>
);
export const Chevron = (p: P) => (
  <Svg {...p}>
    <path d="M6 9l6 6 6-6" />
  </Svg>
);
export const Check = (p: P) => (
  <Svg {...p}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Svg>
);
export const ArrowUp = (p: P) => (
  <Svg {...p}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </Svg>
);
export const Panel = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M15 4v16" />
  </Svg>
);
export const Logout = ({ className = "", ...p }: P) => (
  <Svg {...p} className={`flip ${className}`}>
    <path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 8l-4 4 4 4M6 12h10" />
  </Svg>
);
export const User = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" />
  </Svg>
);
export const Team = (p: P) => (
  <Svg {...p}>
    <circle cx="9" cy="8" r="3.5" />
    <path d="M2.5 20c1-3.5 3.6-5.5 6.5-5.5s5.5 2 6.5 5.5" />
    <path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c1.7.7 3 2.5 3.5 5.2" />
  </Svg>
);
export const Feed = (p: P) => (
  <Svg {...p}>
    <path d="M5 5a14 14 0 0 1 14 14M5 11a8 8 0 0 1 8 8" />
    <circle cx="6" cy="18" r="1.5" />
  </Svg>
);
export const Radar = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="1.6" fill="currentColor" />
    <path d="M12 3a9 9 0 1 0 9 9" />
    <path d="M12 7.5a4.5 4.5 0 1 0 4.5 4.5" />
    <path d="M12 12l6-6" />
  </Svg>
);
export const Mail = (p: P) => (
  <Svg {...p}>
    <path d="M4 7l8 6 8-6" />
    <rect x="3" y="5" width="18" height="14" rx="2" />
  </Svg>
);
export const StateOk = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M8 12.5l3 3 5-6" />
  </Svg>
);
export const Clock = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Svg>
);
export const StateStopped = (p: P) => (
  <Svg {...p}>
    <path d="M8 3h8l5 5v8l-5 5H8l-5-5V8z" />
    <path d="M9.5 9.5l5 5M14.5 9.5l-5 5" />
  </Svg>
);
export const Alert = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v6M12 16.5v.5" />
  </Svg>
);
export const BrokenLink = (p: P) => (
  <Svg {...p}>
    <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" />
    <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
    <path d="M4 4l16 16" />
  </Svg>
);
export const Plus = (p: P) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <Svg size={size} width={2.4} className="spin">
      <path d="M12 3a9 9 0 1 0 9 9" />
    </Svg>
  );
}

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <span className="logo" style={{ width: size, height: size, borderRadius: size > 34 ? 10 : 8 }}>
      <svg
        width={size * 0.66}
        height={size * 0.66}
        viewBox="0 0 24 24"
        fill="none"
        stroke="#1A1600"
        strokeWidth="2.2"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="1.8" fill="#1A1600" stroke="none" />
        <path d="M12 4a8 8 0 1 0 8 8" />
        <path d="M12 8a4 4 0 1 0 4 4" />
        <path d="M12 12l6.5-6.5" />
      </svg>
    </span>
  );
}
